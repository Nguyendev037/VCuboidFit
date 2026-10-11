import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const budget = Number(body.budget) || 50;
    const source = body.source || "synthetic";
    const runName = body.runName || `run_b${budget}_${Date.now()}`;

    const repoRoot = path.resolve(process.cwd(), "..");
    const v2Dir = path.join(repoRoot, "rare_frame_mining");
    const venvPython = path.join(repoRoot, "model", "worker", ".venv", "bin", "python");

    const pythonBin = fs.existsSync(venvPython) ? venvPython : "python3";
    const outDir = path.join(v2Dir, runName);

    // Chạy scripts/run_pipeline.py
    const runScript = path.join(v2Dir, "scripts", "run_pipeline.py");
    const evalScript = path.join(v2Dir, "scripts", "run_eval.py");

    const args = [
      runScript,
      "--source",
      source,
      "--budget",
      String(budget),
      "--out",
      runName,
    ];

    if (body.dataroot) {
      args.push("--dataroot", body.dataroot);
      if (body.version) args.push("--version", body.version);
    }

    const runOutput = await new Promise<string>((resolve, reject) => {
      const child = spawn(pythonBin, args, { cwd: v2Dir });
      let output = "";
      child.stdout.on("data", (d) => { output += d.toString(); });
      child.stderr.on("data", (d) => { output += d.toString(); });
      child.on("close", (code) => {
        if (code === 0) resolve(output);
        else reject(new Error(`run_pipeline failed with code ${code}:\n${output}`));
      });
    });

    // Chạy run_eval.py nếu có
    let evalOutput = "";
    try {
      evalOutput = await new Promise<string>((resolve) => {
        const child = spawn(pythonBin, [evalScript, "--out", runName], { cwd: v2Dir });
        let output = "";
        child.stdout.on("data", (d) => { output += d.toString(); });
        child.stderr.on("data", (d) => { output += d.toString(); });
        child.on("close", () => resolve(output));
      });
    } catch {}

    return NextResponse.json({
      success: true,
      runName,
      outDir,
      runOutput,
      evalOutput,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: errorMsg }, { status: 500 });
  }
}
