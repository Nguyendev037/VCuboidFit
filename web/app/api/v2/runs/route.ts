import { NextRequest, NextResponse } from "next/server";
import path from "path";
import fs from "fs";

function parseCsv(content: string): Record<string, string>[] {
  const lines = content.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const values: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let c = 0; c < line.length; c++) {
      const char = line[c];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        values.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    values.push(current.trim());
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => {
      obj[h] = values[idx] ?? "";
    });
    rows.push(obj);
  }
  return rows;
}

export async function GET(req: NextRequest) {
  try {
    const rootDir = path.resolve(process.cwd(), "..", "rare_frame_mining");
    if (!fs.existsSync(rootDir)) {
      return NextResponse.json({ error: "Thư mục rare_frame_mining không tồn tại" }, { status: 404 });
    }

    // Tìm tất cả các thư mục chứa kết quả chạy
    const entries = fs.readdirSync(rootDir, { withFileTypes: true });
    const availableRuns: string[] = [];
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const checkFile = path.join(rootDir, entry.name, "frames_ranked_T.csv");
        if (fs.existsSync(checkFile)) {
          availableRuns.push(entry.name);
        }
      }
    }

    const { searchParams } = new URL(req.url);
    const selectedRun = searchParams.get("run") || availableRuns[0] || "outputs_test";
    const targetDir = path.join(rootDir, selectedRun);

    if (!fs.existsSync(targetDir)) {
      return NextResponse.json({
        availableRuns,
        selectedRun,
        error: `Không tìm thấy thư mục kết quả: ${selectedRun}`,
      });
    }

    let report = null;
    let summary = null;
    let configUsed = null;
    let frames: Record<string, string>[] = [];
    let objects: Record<string, string>[] = [];
    let review: Record<string, string>[] = [];

    const reportPath = path.join(targetDir, "report.json");
    if (fs.existsSync(reportPath)) {
      try {
        report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
      } catch {}
    }

    const summaryPath = path.join(targetDir, "summary.json");
    if (fs.existsSync(summaryPath)) {
      try {
        summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
      } catch {}
    }

    const configPath = path.join(targetDir, "config_used.json");
    if (fs.existsSync(configPath)) {
      try {
        configUsed = JSON.parse(fs.readFileSync(configPath, "utf8"));
      } catch {}
    }

    const framesPath = path.join(targetDir, "frames_ranked_T.csv");
    if (fs.existsSync(framesPath)) {
      frames = parseCsv(fs.readFileSync(framesPath, "utf8"));
    }

    const objectsPath = path.join(targetDir, "objects_T.csv");
    if (fs.existsSync(objectsPath)) {
      objects = parseCsv(fs.readFileSync(objectsPath, "utf8"));
    }

    const reviewPath = path.join(targetDir, "review_T.csv");
    if (fs.existsSync(reviewPath)) {
      review = parseCsv(fs.readFileSync(reviewPath, "utf8"));
    }

    return NextResponse.json({
      availableRuns,
      selectedRun,
      report,
      summary,
      configUsed,
      frames,
      objects,
      review,
    });
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: errorMsg }, { status: 500 });
  }
}
