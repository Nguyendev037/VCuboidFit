import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import type { ReactElement } from "react";
import type { ComponentProps } from "react";
import { UPLOAD_HELP } from "@/lib/glossary";
import { GB_BYTES } from "@/lib/onlineUpload";
import { uploadSelection } from "./uploadSelection";

const hooks = vi.hoisted(() => ({ values: [] as unknown[], cursor: 0 }));
vi.mock("react", async (original) => ({
  ...await original<typeof import("react")>(),
  useEffect: () => {},
  useState: (initial: unknown) => {
    const index = hooks.cursor++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => { hooks.values[index] = value; }];
  },
}));
import { UploadPanel } from "./UploadPanel";

type Element = ReactElement<Record<string, unknown>>;
function find(node: unknown, predicate: (node: Element) => boolean): Element | undefined {
  if (Array.isArray(node)) {
    for (const child of node) { const result = find(child, predicate); if (result) return result; }
  } else if (node && typeof node === "object" && "props" in node) {
    const element = node as Element;
    if (predicate(element)) return element;
    return find(element.props.children, predicate);
  }
}
afterEach(() => { vi.unstubAllEnvs(); hooks.values = []; hooks.cursor = 0; });

describe("A12 online upload consent", () => {
  it("holds a fake 6 GB file until the confirmation button is pressed", () => {
    vi.stubEnv("NEXT_PUBLIC_VCF_SESSIONS", "1");
    const startUpload = vi.fn();
    const props = {
      uploadIdRef: { current: undefined }, fileInputRef: { current: null },
      setItems: vi.fn(), setDataset: vi.fn(), startUpload, items: [], uploading: false,
    } as unknown as ComponentProps<typeof UploadPanel>;
    const render = () => { hooks.cursor = 0; return UploadPanel(props); };
    const first = render();
    const input = find(first, (node) => node.props["data-testid"] === "file-input")!;
    const file = { name: "large.zip", size: 6 * GB_BYTES } as File;
    (input.props.onChange as (event: unknown) => void)({ target: { files: [file], value: "large.zip" } });
    expect(startUpload).not.toHaveBeenCalled();
    const warning = render();
    expect(find(warning, (node) => node.type === "p" && node.props.children === UPLOAD_HELP.notice.online.confirmWarning)).toBeDefined();
    const button = find(warning, (node) => node.type === "button" && node.props.children === UPLOAD_HELP.notice.online.confirm)!;
    (button.props.onClick as () => void)();
    expect(startUpload).toHaveBeenCalledExactlyOnceWith([file]);
  });
  it("uses strict binary GB thresholds and leaves local uploads unchanged", () => {
    expect(uploadSelection(GB_BYTES, true)).toEqual({ warning: false, confirm: false });
    expect(uploadSelection(5 * GB_BYTES, true)).toEqual({ warning: true, confirm: false });
    expect(uploadSelection(6 * GB_BYTES, false)).toEqual({ warning: false, confirm: false });
  });
});

describe("A13 nuScenes checklist", () => {
  it("matches REQUIRED and OPTIONAL Python tables exactly", () => {
    const source = readFileSync(new URL("../../../model/worker/c4/data/nusc.py", import.meta.url), "utf8");
    const names = (key: string) => JSON.parse(source.match(new RegExp(`^${key} = (\\[.*\\])$`, "m"))![1]);
    expect(UPLOAD_HELP.notice.checklist[0].files).toEqual(names("REQUIRED"));
    expect(UPLOAD_HELP.notice.checklist[1].files).toEqual(names("OPTIONAL"));
    expect(UPLOAD_HELP.notice.checklist.map((item) => item.path)).not.toContain("data/maps/");
  });
});
