using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace TL2_Mikuro_Console
{
    internal class Program
    {
        // --profile-init: poll EditorGetLoadStatus on a side thread while InitEditor
        // runs, to break the ~5s cold init into its load phases (INIT_PHASE lines).
        static bool s_profileInit;

        static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            s_profileInit = args.Any(a => a.Equals("--profile-init", StringComparison.OrdinalIgnoreCase));
            EditorDLL.EditorSteamLoggedIn();
            Console.WriteLine(EditorDLL.IsSteamLoggedOn());
            InitDLL();

            string modsPath = AppDomain.CurrentDomain.BaseDirectory + "mods";

            // Non-interactive test-helper mode (used by the verification harness):
            //   build <mod> | build-all | regen-mpp <mod>   [--clean] [--twice]
            if (args.Length > 0)
            {
                RunBatch(args, modsPath);
                DeleteOldLogFiles();
                return;
            }

            string userInput = string.Empty;

            while (userInput != ":q")
            {
                Console.ForegroundColor = ConsoleColor.Yellow;
                List<string> modList = GetImmediateSubfolderNames(modsPath);
                for (int i = 0; i < modList.Count; i++)
                {
                    Console.WriteLine(i.ToString().PadLeft(2, ' ') + ": " + modList[i]);
                }
                Console.ForegroundColor = ConsoleColor.Green;
                Console.Write("📝Type ':q' to quit or select MOD number you would like to build->");
                Console.ResetColor();

                userInput = Console.ReadLine();
                if (int.TryParse(userInput, out int inputNum))
                {
                    if (inputNum >= 0 && inputNum < modList.Count)
                    {
                        string modPath = modsPath + @"\" + modList[inputNum] + @"\MOD.DAT";
                        EditorDLL.EditorSetWorkingMod(modsPath + @"\" + modList[inputNum]);
                        string buildStartTime = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
                        bool buildResult = EditorDLL.CreateMod(modPath, true);
                        string buildEndTime = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
                        Console.ForegroundColor = ConsoleColor.Yellow;
                        Console.WriteLine($"🚀Build: {modPath}");
                        Console.ResetColor();
                        if (buildResult)
                        {
                            Console.ForegroundColor = ConsoleColor.Green;
                            Console.WriteLine($"🎉Sucess");
                            Console.WriteLine($"💡Start: {buildStartTime}");
                            Console.WriteLine($"💡End:   {buildEndTime}");
                        }
                        else
                        {
                            Console.ForegroundColor = ConsoleColor.Red;
                            Console.WriteLine("💥Fail, check log for what happen");
                        }
                        Console.ResetColor();
                    }
                }
                else
                {
                    if (userInput=="MPP")
                    {
                        //EditorDLL.EditorRegenPathingDataSingleFile(@"E:\Program Files (x86)\Steam\steamapps\common\Torchlight II\mods\MIKURO_FUN\MEDIA\LAYOUTS\TEST.LAYOUT");
                        EditorDLL.EditorRegenPathingData(@"E:\Program Files (x86)\Steam\steamapps\common\Torchlight II\mods\MIKURO_FUN\MEDIA\LAYOUTS\");
                    }
                    if (userInput == "TEST")
                    {
                        Console.WriteLine(EditorDLL.GetPlayerStatData());
                    }
                    else
                    {
                        Console.WriteLine(userInput != ":q" ? "🚨Unsupported input" : "");
                    }
                }
            }
            DeleteOldLogFiles();
            Console.WriteLine("💡Goodbye!");
        }

        // Files the harness wants regenerated from scratch by GUTS each run.
        static readonly string[] CleanExts = { ".BINDAT", ".BINLAYOUT", ".RAW", ".MPP", ".MOD" };

        static void CleanMod(string modDir)
        {
            int n = 0;
            foreach (string f in Directory.EnumerateFiles(modDir, "*", SearchOption.AllDirectories))
            {
                if (Array.IndexOf(CleanExts, Path.GetExtension(f).ToUpperInvariant()) >= 0)
                {
                    try { File.Delete(f); n++; } catch { }
                }
            }
            Console.WriteLine($"🧹Cleaned {n} bin/mpp/raw/mod files in {Path.GetFileName(modDir)}");
        }

        static bool BuildMod(string modsPath, string modName, bool clean, bool twice)
        {
            string modDir = Path.Combine(modsPath, modName);
            string modDat = Path.Combine(modDir, "MOD.DAT");
            if (!File.Exists(modDat))
            {
                Console.WriteLine($"❌No MOD.DAT in {modName}");
                return false;
            }
            if (clean) CleanMod(modDir);

            EditorDLL.EditorSetWorkingMod(modDir);
            bool ok = EditorDLL.CreateMod(modDat, true);
            // A clean (no .BINLAYOUT) build makes GUTS emit degenerate ~2.5KB MPPs
            // on the first pass; a second pass — once BINLAYOUTs exist — fixes them.
            if (twice)
            {
                EditorDLL.EditorSetWorkingMod(modDir);
                ok = EditorDLL.CreateMod(modDat, true);
            }
            Console.WriteLine($"{(ok ? "🎉" : "💥")} {modName}: {EditorDLL.GetModCreateMessage()}");
            return ok;
        }

        static void BenchMod(string modsPath, string modName, bool clean)
        {
            string modDir = Path.Combine(modsPath, modName);
            string modDat = Path.Combine(modDir, "MOD.DAT");
            if (!File.Exists(modDat)) { Console.WriteLine($"BENCH,{modName},,,no-MOD.DAT"); return; }
            string layoutsDir = Path.Combine(modDir, "MEDIA", "LAYOUTS");
            try
            {
                if (clean) CleanMod(modDir);
                // Full build: compile (BINDAT/BINLAYOUT) + RAW + pack. One CreateMod pass
                // (NOT --twice) so build_ms maps to compile+RAW+pack; it writes BINLAYOUT so
                // the following RegenPathing produces correct (non-stub) .mpp.
                EditorDLL.EditorSetWorkingMod(modDir);
                var sw1 = Stopwatch.StartNew();
                bool ok = EditorDLL.CreateMod(modDat, true);
                double buildMs = sw1.Elapsed.TotalMilliseconds;
                // Isolated MPP: real byte-exact pathing regen over this mod's level layouts.
                double mppMs = 0;
                if (Directory.Exists(layoutsDir))
                {
                    EditorDLL.EditorSetWorkingMod(modDir);
                    var sw2 = Stopwatch.StartNew();
                    EditorDLL.EditorRegenPathingData(layoutsDir + "\\");
                    mppMs = sw2.Elapsed.TotalMilliseconds;
                }
                Console.WriteLine($"BENCH,{modName},{buildMs:F1},{mppMs:F1},{ok}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"BENCH,{modName},,,ERR:{ex.Message}");
            }
        }

        static void RunBatch(string[] args, string modsPath)
        {
            var flags = new HashSet<string>(args.Where(a => a.StartsWith("--")), StringComparer.OrdinalIgnoreCase);
            var pos = args.Where(a => !a.StartsWith("--")).ToList();
            bool clean = flags.Contains("--clean");
            bool twice = flags.Contains("--twice");
            string cmd = pos.Count > 0 ? pos[0].ToLowerInvariant() : "";

            if (cmd == "build-all")
            {
                foreach (string m in GetImmediateSubfolderNames(modsPath))
                    BuildMod(modsPath, m, clean, twice);
            }
            else if (cmd == "build" && pos.Count > 1)
            {
                BuildMod(modsPath, pos[1], clean, twice);
            }
            else if (cmd == "regen-mpp" && pos.Count > 1)
            {
                string layouts = Path.Combine(modsPath, pos[1], "MEDIA", "LAYOUTS") + "\\";
                EditorDLL.EditorRegenPathingData(layouts);
                Console.WriteLine($"🧭MPP regen done for {pos[1]}");
            }
            else if (cmd == "bench")
            {
                // WARM batch: InitEditor was paid ONCE in Main; here we time each mod's
                // CreateMod (compile + RAW + pack, writes BINLAYOUT) and EditorRegenPathingData
                // (real byte-exact MPP) separately. The first mod includes cold data-load and
                // should be treated as warm-up. Emits machine-parseable BENCH,<mod>,<build_ms>,
                // <mpp_ms>,<ok> lines. Mods are taken from `--all` or the positional list; the
                // caller (Python) stages scratch copies under mods/ for non-destructive runs.
                var mods = flags.Contains("--all") ? GetImmediateSubfolderNames(modsPath)
                                                   : pos.Skip(1).ToList();
                Console.WriteLine("BENCH_HEADER,mod,build_ms,mpp_ms,ok");
                foreach (string m in mods)
                    BenchMod(modsPath, m, clean);
                Console.WriteLine("BENCH_DONE");
            }
            else
            {
                Console.WriteLine("Usage: TL2-Mikuro-Console <command> [--clean] [--twice] [--all]");
                Console.WriteLine("  build <mod>     build one mod via GUTS");
                Console.WriteLine("  build-all       build every mod under mods/");
                Console.WriteLine("  regen-mpp <mod> regenerate .MPP pathing data only");
                Console.WriteLine("  bench <mods...> WARM per-mod timing: CreateMod + RegenPathing,");
                Console.WriteLine("                  init amortized once (use --all for every mod)");
                Console.WriteLine("  --clean         delete .BINDAT/.BINLAYOUT/.RAW/.MPP/.MOD first");
                Console.WriteLine("  --twice         build twice (fixes clean-build MPP degeneracy)");
            }
        }

        //https://stackoverflow.com/questions/1277563/how-do-i-get-the-handle-of-a-console-applications-window
        [DllImport("kernel32.dll")]
        static extern IntPtr GetConsoleWindow();

        static void InitDLL()
        {
            try
            {
                int hlnst = Marshal.GetHINSTANCE(typeof(Program).Module).ToInt32();
                IntPtr hWnd = GetConsoleWindow();
                Console.WriteLine($"💡Instance Handle: {hlnst}");
                Console.WriteLine($"💡Process Handle: {hWnd}");
                string t1 = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
                //EditorDLL.EditorSetWorkingMod(@"E:\Program Files (x86)\Steam\steamapps\common\Torchlight II\mods\MIKURO_FUN");
                var swInit = Stopwatch.StartNew();
                // Phase profiler: a side thread samples the editor's load-status string
                // (EditorGetLoadStatus) every 20ms while InitEditor blocks on the main
                // thread; each change is timestamped. Gated by --profile-init.
                var phases = s_profileInit ? new List<string>() : null;
                if (s_profileInit)
                {
                    var poller = new Thread(() =>
                    {
                        string last = null;
                        while (swInit.IsRunning)
                        {
                            string s = null;
                            try { s = EditorDLL.EditorGetLoadStatus(); } catch { }
                            if (!string.IsNullOrEmpty(s) && s != last)
                            {
                                lock (phases) phases.Add($"{swInit.Elapsed.TotalMilliseconds:F0},{s.Replace(',', ' ').Replace('\n', ' ')}");
                                last = s;
                            }
                            Thread.Sleep(20);
                        }
                    }) { IsBackground = true };
                    poller.Start();
                }
                int initFlag = EditorDLL.InitEditor(hlnst, hWnd.ToInt32());
                swInit.Stop();
                if (s_profileInit && phases != null)
                {
                    Thread.Sleep(40);   // let the poller record the final status
                    Console.WriteLine("INIT_PROFILE_BEGIN");
                    lock (phases) foreach (var p in phases) Console.WriteLine("INIT_PHASE," + p);
                    Console.WriteLine($"INIT_PHASE,{swInit.Elapsed.TotalMilliseconds:F0},<InitEditor returned>");
                    Console.WriteLine("INIT_PROFILE_END");
                }
                if (initFlag == 1)
                {
                    string t2 = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
                    Console.ForegroundColor = ConsoleColor.Green;
                    Console.WriteLine($"✅Init S: {t1}");
                    Console.WriteLine($"✅Init E: {t2}");
                    Console.WriteLine("✅GUTS Editor's DLL init finished.");
                    Console.ResetColor();
                    // machine-parseable: the one-time editor init cost (amortized across a batch)
                    Console.WriteLine($"INIT_MS,{swInit.Elapsed.TotalMilliseconds:F1}");
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.DarkRed;
                Console.WriteLine("🚨GUTS Editor's DLL init failed.");
                Console.ResetColor();
                Console.Error.WriteLine(ex.Message);
            }
        }

        static List<string> GetImmediateSubfolderNames(string path)
        {
            string[] subdirectories = Directory.GetDirectories(path);
            List<string> folderNames = new List<string>();

            foreach (string subdirectory in subdirectories)
            {
                string folderName = Path.GetFileName(subdirectory);
                folderNames.Add(folderName);
            }

            return folderNames;
        }

        static void DeleteOldLogFiles()
        {
            var pathWithEnv = @"%USERPROFILE%\Documents\my games\runic games\torchlight 2\logs";
            var logsPath = Environment.ExpandEnvironmentVariables(pathWithEnv);
            DateTime today = DateTime.Today;
            try
            {
                foreach (string filePath in Directory.GetFiles(logsPath))
                {
                    FileInfo fileInfo = new FileInfo(filePath);
                    if (fileInfo.LastWriteTime < today)
                    {
                        File.Delete(filePath);
                        Console.WriteLine($"🗑️Deleted out-dated log: {filePath}");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }
        }
    }
}
