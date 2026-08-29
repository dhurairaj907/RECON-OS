/**
 * Cheap one-shot WebGL capability probe. Used to decide whether to mount a
 * <Canvas> at all — if it returns false we fall back to the CSS/SVG pipeline.
 */
let cached: boolean | null = null;

export function isWebGLAvailable(): boolean {
  if (cached != null) return cached;
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    cached = !!gl;
  } catch {
    cached = false;
  }
  return cached;
}
