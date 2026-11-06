// Disposable native smoke fixture, never included in the application ZIP.
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading;

class GitShutdownShim {
    static int Main(string[] args) {
        if (Array.IndexOf(args, "--version") >= 0) {
            Console.WriteLine("git version 2.56.0.windows.2");
            return 0;
        }
        string root = Environment.GetEnvironmentVariable("COMMITANDSEE_SHUTDOWN_FIXTURE");
        bool child = args.Length > 0 && args[0] == "--fixture-child";
        File.WriteAllText(Path.Combine(root, child ? "child.pid" : "git.pid"),
                         Process.GetCurrentProcess().Id.ToString());
        if (!child) {
            var start = new ProcessStartInfo(Assembly.GetExecutingAssembly().Location, "--fixture-child");
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
        }
        Thread.Sleep(120000);
        return 0;
    }
}
