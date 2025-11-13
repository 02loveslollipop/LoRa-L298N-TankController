import { useMemo } from "react";
import { useWhepPlayer } from "../../hooks/useWhepPlayer";

interface WhepPlayerProps {
  whepUrl: string;
  className?: string;
}

export function WhepPlayer({ whepUrl, className }: WhepPlayerProps) {
  const iceServers = useMemo(
    () => [{ urls: "stun:stun.l.google.com:19302" }],
    []
  );

  const { videoRef, state, error } = useWhepPlayer({ whepUrl, iceServers });

  return (
    <div className={className}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        controls
        style={{ width: "100%", backgroundColor: "black" }}
      />
      <div style={{ marginTop: "0.5rem", color: "white" }}>
        {state === "connecting" && "Connecting to stream…"}
        {state === "playing" && "Live"}
        {state === "error" && (
          <span style={{ color: "salmon" }}>Error: {error}</span>
        )}
      </div>
    </div>
  );
}
