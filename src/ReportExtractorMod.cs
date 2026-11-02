using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using HarmonyLib;
using KMod;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;

namespace OniReportExtractor
{
    public class ModInit : UserMod2
    {
        public override void OnLoad(Harmony harmony)
        {
            // UserMod2.OnLoad chama harmony.PatchAll() para este assembly.
            base.OnLoad(harmony);
            Debug.Log("[ReportExtractor] Carregado. Exportando para: " + ReportExporter.ExportDir);
        }
    }

    public class CycleReportDto
    {
        public int SchemaVersion { get; set; }
        public string ColonyName { get; set; }
        public string ColonyId { get; set; }
        public int Cycle { get; set; }
        public string Timestamp { get; set; }
        public List<ReportEntryDto> Entries { get; set; }
        public SnapshotDto Snapshot { get; set; }

        public CycleReportDto() { Entries = new List<ReportEntryDto>(); }
    }

    public class ReportEntryDto
    {
        public string Category { get; set; }
        // Nulo na linha agregada; preenchido nas linhas de detalhe (duplicante, construção etc.).
        public string Context { get; set; }
        public float NetValue { get; set; }
        public float PositiveValue { get; set; }
        public float NegativeValue { get; set; }
        [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
        public List<NoteDto> Notes { get; set; }
    }

    public class NoteDto
    {
        public string Note { get; set; }
        public float Value { get; set; }
    }

    public class SnapshotDto
    {
        public double CaptureMs { get; set; }
        public List<string> Errors { get; set; }
        public List<WorldSnapshotDto> Worlds { get; set; }
        public List<DuplicantSnapshotDto> Duplicants { get; set; }
        public SnapshotDto()
        {
            Errors = new List<string>();
            Worlds = new List<WorldSnapshotDto>();
            Duplicants = new List<DuplicantSnapshotDto>();
        }
    }

    public class WorldSnapshotDto
    {
        public int WorldId { get; set; }
        public string WorldName { get; set; }
        public float RationKcalRaw { get; set; }
        public float TrackerKcalRaw { get; set; }
        public float BatteryJoules { get; set; }
        public float BatteryCapacityJoules { get; set; }
        public float TrackerBatteryRaw { get; set; }
        public List<MaterialDto> Materials { get; set; }
        public WorldSnapshotDto() { Materials = new List<MaterialDto>(); }
    }

    public class MaterialDto
    {
        public string Tag { get; set; }
        public float Kg { get; set; }
    }

    public class DuplicantSnapshotDto
    {
        public string Name { get; set; }
        public int WorldId { get; set; }
        public float Stress { get; set; }
    }

    // No U51 o método é "OnNightTime" (T maiúsculo). Com o nome errado o PatchAll lança exceção ao carregar.
    [HarmonyPatch(typeof(ReportManager), "OnNightTime")]
    public static class ReportManager_OnNightTime_Patch
    {
        public static void Postfix()
        {
            try
            {
                // OnNightTime fecha o todaysReport e o adiciona em dailyReports; YesterdaysReport é o ciclo recém-fechado.
                ReportManager.DailyReport dailyReport = ReportManager.Instance.YesterdaysReport;
                if (dailyReport == null) return;

                CycleReportDto dto = new CycleReportDto();
                dto.SchemaVersion = 2;
                dto.Cycle = dailyReport.day;
                dto.Timestamp = System.DateTime.Now.ToString("o");
                List<string> noteErrors = new List<string>();
                try
                {
                    dto.ColonyName = SaveLoader.Instance.GameInfo.baseName;
                    dto.ColonyId = SaveLoader.Instance.GameInfo.colonyGuid.ToString();
                    if (String.IsNullOrEmpty(dto.ColonyId) || dto.ColonyId == Guid.Empty.ToString())
                        dto.ColonyId = SafeFileName(dto.ColonyName);
                }
                catch (Exception ex)
                {
                    dto.ColonyId = SafeFileName(dto.ColonyName);
                    if (String.IsNullOrEmpty(dto.ColonyId)) dto.ColonyId = "sem_id";
                    Debug.LogError("[ReportExtractor] Erro lendo identificação da colônia: " + ex.Message);
                }

                foreach (ReportManager.ReportEntry entry in dailyReport.reportEntries)
                {
                    string category = entry.reportType.ToString();
                    ReportEntryDto total = new ReportEntryDto
                    {
                        Category = category,
                        NetValue = entry.Net,
                        PositiveValue = entry.Positive,
                        NegativeValue = entry.Negative
                    };
                    dto.Entries.Add(total);
                    AddNotes(entry, total, category, noteErrors);

                    // contextEntries é um ArrayRef<> (struct da Klei, sem enumerador): itera por índice.
                    for (int i = 0; i < entry.contextEntries.Count; i++)
                    {
                        ReportManager.ReportEntry ctx = entry.contextEntries[i];
                        ReportEntryDto detail = new ReportEntryDto
                        {
                            Category = category,
                            Context = ctx.context,
                            NetValue = ctx.Net,
                            PositiveValue = ctx.Positive,
                            NegativeValue = ctx.Negative
                        };
                        dto.Entries.Add(detail);
                        AddNotes(ctx, detail, category, noteErrors);
                    }
                }

                dto.Snapshot = CaptureSnapshot();
                dto.Snapshot.Errors.AddRange(noteErrors);
                ReportExporter.Write(dto);
            }
            catch (Exception ex) { Debug.LogError("[ReportExtractor] Erro: " + ex); }
        }

        private static string SafeFileName(string value)
        {
            if (String.IsNullOrEmpty(value)) return "sem_id";
            char[] invalid = Path.GetInvalidFileNameChars();
            StringBuilder safe = new StringBuilder(value.Length);
            for (int i = 0; i < value.Length; i++)
            {
                bool replace = false;
                for (int j = 0; j < invalid.Length; j++) if (value[i] == invalid[j]) { replace = true; break; }
                safe.Append(replace ? '_' : value[i]);
            }
            return safe.Length == 0 ? "sem_id" : safe.ToString();
        }

        private static void AddNotes(ReportManager.ReportEntry entry, ReportEntryDto dto, string category, List<string> errors)
        {
            if (category != "EnergyCreated" && category != "EnergyWasted" && category != "OxygenCreated") return;
            try
            {
                List<NoteDto> notes = new List<NoteDto>();
                entry.IterateNotes(delegate(ReportManager.ReportEntry.Note note)
                {
                    notes.Add(new NoteDto { Note = note.note, Value = note.value });
                });
                if (notes.Count > 0) dto.Notes = notes;
            }
            catch (Exception ex) { errors.Add("Notas " + category + ": " + ex.Message); }
        }

        private static SnapshotDto CaptureSnapshot()
        {
            Stopwatch watch = Stopwatch.StartNew();
            SnapshotDto snapshot = new SnapshotDto();
            try
            {
                foreach (WorldContainer world in ClusterManager.Instance.WorldContainers)
                {
                    try
                    {
                        if (!world.IsDiscovered) continue;
                        WorldSnapshotDto item = new WorldSnapshotDto { WorldId = world.id, WorldName = world.GetProperName() };
                        try { item.RationKcalRaw = RationTracker.Get().CountAmount(new Dictionary<string, float>(), world.worldInventory, true); }
                        catch (Exception ex) { snapshot.Errors.Add("World " + world.id + " RationKcalRaw: " + ex.Message); }
                        try { item.TrackerKcalRaw = TrackerTool.Instance.GetWorldTracker<KCalTracker>(world.id).GetCurrentValue(); }
                        catch (Exception ex) { snapshot.Errors.Add("World " + world.id + " TrackerKcalRaw: " + ex.Message); }
                        try
                        {
                            foreach (Battery battery in Components.Batteries.Items)
                            {
                                if (battery.GetMyWorldId() == world.id)
                                {
                                    item.BatteryJoules += battery.JoulesAvailable;
                                    item.BatteryCapacityJoules += battery.Capacity;
                                }
                            }
                        }
                        catch (Exception ex) { snapshot.Errors.Add("World " + world.id + " bateria soma: " + ex.Message); }
                        try { item.TrackerBatteryRaw = TrackerTool.Instance.GetWorldTracker<BatteryTracker>(world.id).GetCurrentValue(); }
                        catch (Exception ex) { snapshot.Errors.Add("World " + world.id + " TrackerBatteryRaw: " + ex.Message); }
                        AddMaterials(item, world, snapshot.Errors);
                        snapshot.Worlds.Add(item);
                    }
                    catch (Exception ex) { snapshot.Errors.Add("World: " + ex.Message); }
                }
            }
            catch (Exception ex) { snapshot.Errors.Add("Mundos: " + ex.Message); }
            try
            {
                foreach (MinionIdentity minion in Components.LiveMinionIdentities.Items)
                {
                    try
                    {
                        snapshot.Duplicants.Add(new DuplicantSnapshotDto
                        {
                            Name = minion.GetProperName(),
                            WorldId = minion.GetMyWorldId(),
                            Stress = Db.Get().Amounts.Stress.Lookup(minion).value
                        });
                    }
                    catch (Exception ex) { snapshot.Errors.Add("Duplicante: " + ex.Message); }
                }
            }
            catch (Exception ex) { snapshot.Errors.Add("Duplicantes: " + ex.Message); }
            watch.Stop();
            snapshot.CaptureMs = watch.Elapsed.TotalMilliseconds;
            return snapshot;
        }

        private static void AddMaterials(WorldSnapshotDto item, WorldContainer world, List<string> errors)
        {
            SimHashes[] hashes = { SimHashes.Algae, SimHashes.Carbon, SimHashes.Cuprite, SimHashes.Copper,
                SimHashes.GoldAmalgam, SimHashes.IronOre, SimHashes.Iron };
            foreach (SimHashes hash in hashes)
            {
                try
                {
                    float amount = world.worldInventory.GetAmount(hash.CreateTag(), false);
                    item.Materials.Add(new MaterialDto { Tag = hash.ToString(), Kg = amount });
                }
                catch (Exception ex) { errors.Add("World " + world.id + " material " + hash + ": " + ex.Message); }
            }
        }
    }

    public static class ReportExporter
    {
        // Manager.GetDirectory() = <Documentos>\Klei\OxygenNotIncluded\mods\ (respeita redirecionamento do OneDrive).
        public static readonly string ExportDir = Path.GetFullPath(Path.Combine(Path.Combine(Manager.GetDirectory(), ".."), "export"));
        public const bool WriteLegacyRoot = true;

        public static void Write(CycleReportDto reportData)
        {
            string json = JsonConvert.SerializeObject(reportData, Formatting.Indented);
            string colonyDir = Path.Combine(Path.Combine(ExportDir, "colonies"), reportData.ColonyId);
            WriteOne(colonyDir, "report_cycle_" + reportData.Cycle + ".json", json);
            if (WriteLegacyRoot) WriteOne(ExportDir, "report_cycle_" + reportData.Cycle + ".json", json);
        }

        private static void WriteOne(string directory, string fileName, string json)
        {
            string path = Path.Combine(directory, fileName);
            string tmp = path + ".tmp";
            // Grava em .tmp e renomeia, para o Power Query/Python nunca ler um JSON pela metade.
            try
            {
                Directory.CreateDirectory(directory);
                for (int attempt = 0; attempt < 3; attempt++)
                {
                    try
                    {
                        File.WriteAllText(tmp, json, new UTF8Encoding(false));
                        if (File.Exists(path)) File.Replace(tmp, path, null);
                        else File.Move(tmp, path);
                        return;
                    }
                    catch (IOException) { if (attempt == 2) throw; System.Threading.Thread.Sleep(50); }
                    catch (UnauthorizedAccessException) { if (attempt == 2) throw; System.Threading.Thread.Sleep(50); }
                }
            }
            catch (Exception ex) { Debug.LogError("[ReportExtractor] Erro gravando " + path + ": " + ex.Message); }
            finally { try { if (File.Exists(tmp)) File.Delete(tmp); } catch { } }
        }
    }
}
