import { ImageResponse } from "next/og";

export const alt = "Ask Graham — every Paul Graham essay, searchable and filterable by startup stage";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#18181b",
          color: "#f4f4f5",
          padding: "72px 80px",
        }}
      >
        <div style={{ display: "flex", fontSize: 30, color: "#a1a1aa" }}>essays by Paul Graham · full text</div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: 96, fontWeight: 700 }}>Ask Graham</div>
          <div style={{ display: "flex", fontSize: 36, color: "#d4d4d8", marginTop: 16 }}>
            Searchable, filterable by startup stage
          </div>
        </div>
        <div style={{ display: "flex", fontSize: 28, color: "#a1a1aa" }}>askgraham.vercel.app</div>
      </div>
    ),
    { ...size },
  );
}
