using System;
using System.Collections.Generic;
using System.IO;
using HarmonyLib;
using KMod;
using Newtonsoft.Json;

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
        public int Cycle { get; set; }
        public string Timestamp { get; set; }
        public List<ReportEntryDto> Entries { get; set; }

        public CycleReportDto()
        {
            Entries = new List<ReportEntryDto>();
        }
    }

    public class ReportEntryDto
    {
        public string Category { get; set; }
        // Nulo na linha agregada; preenchido nas linhas de detalhe (duplicante, construção etc.).
        public string Context { get; set; }
        public float NetValue { get; set; }
        public float PositiveValue { get; set; }
        public float NegativeValue { get; set; }
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

                CycleReportDto dto = new CycleReportDto
                {
                    Cycle = dailyReport.day,
                    Timestamp = System.DateTime.Now.ToString("o")
                };

                foreach (ReportManager.ReportEntry entry in dailyReport.reportEntries)
                {
                    string category = entry.reportType.ToString();
                    dto.Entries.Add(new ReportEntryDto
                    {
                        Category = category,
                        NetValue = entry.Net,
                        PositiveValue = entry.Positive,
                        NegativeValue = entry.Negative
                    });

                    // contextEntries é um ArrayRef<> (struct da Klei, sem enumerador): itera por índice.
                    for (int i = 0; i < entry.contextEntries.Count; i++)
                    {
                        ReportManager.ReportEntry ctx = entry.contextEntries[i];
                        dto.Entries.Add(new ReportEntryDto
                        {
                            Category = category,
                            Context = ctx.context,
                            NetValue = ctx.Net,
                            PositiveValue = ctx.Positive,
                            NegativeValue = ctx.Negative
                        });
                    }
                }

                ReportExporter.Write(dto);
            }
            catch (Exception ex)
            {
                Debug.LogError("[ReportExtractor] Erro: " + ex);
            }
        }
    }

    public static class ReportExporter
    {
        // Manager.GetDirectory() = <Documentos>\Klei\OxygenNotIncluded\mods\ (respeita redirecionamento do OneDrive).
        public static readonly string ExportDir =
            Path.GetFullPath(Path.Combine(Path.Combine(Manager.GetDirectory(), ".."), "export"));

        public static void Write(CycleReportDto reportData)
        {
            Directory.CreateDirectory(ExportDir);

            string filePath = Path.Combine(ExportDir, "report_cycle_" + reportData.Cycle + ".json");
            string tmpPath = filePath + ".tmp";

            // Grava em .tmp e renomeia, para o Power Query/Python nunca ler um JSON pela metade.
            File.WriteAllText(tmpPath, JsonConvert.SerializeObject(reportData, Formatting.Indented));
            if (File.Exists(filePath)) File.Delete(filePath);
            File.Move(tmpPath, filePath);
        }
    }
}
