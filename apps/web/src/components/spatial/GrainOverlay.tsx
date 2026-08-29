import React from "react";

/**
 * Static cinematic film grain. One fixed, non-interactive layer — mounted once
 * in AppShell. No animation, no image asset, no canvas: a single inline-SVG
 * fractal-noise data-URI tiled via CSS. Opacity + blend mode are theme tokens
 * (`--grain-opacity` / `--grain-blend`), so dark gets a stronger tooth than light.
 */
export function GrainOverlay() {
  return <div aria-hidden="true" className="grain-overlay" />;
}
