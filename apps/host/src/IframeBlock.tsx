import React from "react";
export default function IframeBlock({ url }: { url: string }) {
  return (
    <iframe
      src={url}
      style={{ border: 0, width: "100%", height: "calc(100vh - 64px)" }}
      title="Bloco"
    />
  );
}
