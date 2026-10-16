import { GB_BYTES, ONLINE_SOFT_GB, ONLINE_WARN_GB } from "@/lib/onlineUpload";

/** One selection owns its consent; replacing files always resets consent. */
export function uploadSelection(totalBytes: number, online: boolean) {
  return {
    warning: online && totalBytes > ONLINE_SOFT_GB * GB_BYTES,
    confirm: online && totalBytes > ONLINE_WARN_GB * GB_BYTES,
  };
}
