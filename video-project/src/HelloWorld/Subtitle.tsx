import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { COLOR_1, COLOR_ACCENT, FONT_FAMILY } from "./constants";

const subtitle: React.CSSProperties = {
  fontFamily: FONT_FAMILY,
  fontSize: 36,
  textAlign: "center",
  position: "absolute",
  bottom: 120,
  width: "100%",
  letterSpacing: 4,
  textTransform: "uppercase",
};

const badgeStyle: React.CSSProperties = {
  display: "inline-block",
  backgroundColor: COLOR_ACCENT,
  color: "#000",
  padding: "6px 20px",
  borderRadius: 999,
  fontSize: 28,
  fontWeight: "bold",
  marginLeft: 12,
};

export const Subtitle: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1]);
  const slideUp = interpolate(frame, [0, 30], [20, 0]);

  return (
    <div
      style={{
        ...subtitle,
        opacity,
        transform: `translateY(${slideUp}px)`,
      }}
    >
      <span style={{ color: COLOR_1 }}>Built with Remotion</span>
      <span style={badgeStyle}>React</span>
    </div>
  );
};
