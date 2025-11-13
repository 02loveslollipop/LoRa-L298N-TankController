import { useEffect, useRef, useState } from "react";

export interface WhepOptions {
  whepUrl: string;
  iceServers?: RTCIceServer[];
}

export interface WhepPlayer {
  videoRef: React.RefObject<HTMLVideoElement>;
  state: "idle" | "connecting" | "playing" | "error";
  error?: string;
}

export function useWhepPlayer({ whepUrl, iceServers }: WhepOptions): WhepPlayer {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const resourceUrlRef = useRef<string | null>(null);
  const [state, setState] = useState<WhepPlayer["state"]>("idle");
  const [error, setError] = useState<string>();

  useEffect(() => {
    let abort = false;
    const controller = new AbortController();

    async function start() {
      try {
        setState("connecting");
        setError(undefined);

        const pc = new RTCPeerConnection({ iceServers });
        pcRef.current = pc;

        pc.ontrack = evt => {
          if (abort) {
            return;
          }
          const [stream] = evt.streams;
          if (videoRef.current && stream) {
            videoRef.current.srcObject = stream;
            setState("playing");
          }
        };

        pc.onicecandidate = async evt => {
          if (!resourceUrlRef.current || !evt.candidate) {
            return;
          }
          try {
            await fetch(resourceUrlRef.current, {
              method: "PATCH",
              headers: { "Content-Type": "application/trickle-ice-sdpfrag" },
              body: `a=${evt.candidate.candidate}\r\n`
            });
          } catch (err) {
            console.warn("failed to PATCH ICE candidate", err);
          }
        };

        const offer = await pc.createOffer({
          offerToReceiveAudio: true,
          offerToReceiveVideo: true
        });
        await pc.setLocalDescription(offer);

        const response = await fetch(whepUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/sdp",
            Accept: "application/sdp"
          },
          body: offer.sdp,
          signal: controller.signal
        });

        if (!response.ok) {
          throw new Error(`WHEP signaling failed with status ${response.status}`);
        }

        resourceUrlRef.current = response.headers.get("Location");
        const answer = await response.text();
        await pc.setRemoteDescription({ type: "answer", sdp: answer });
      } catch (err) {
        if (abort) {
          return;
        }
        console.error("WHEP setup failed", err);
        setError(err instanceof Error ? err.message : String(err));
        setState("error");
      }
    }

    start();

    return () => {
      abort = true;
      controller.abort();
      resourceUrlRef.current = null;
      if (pcRef.current) {
        pcRef.current.getSenders().forEach(sender => {
          try {
            sender.track?.stop();
          } catch (err) {
            console.warn("failed to stop track", err);
          }
        });
        pcRef.current.ontrack = null;
        pcRef.current.onicecandidate = null;
        pcRef.current.close();
        pcRef.current = null;
      }
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
      setState("idle");
    };
  }, [whepUrl, iceServers]);

  return { videoRef, state, error };
}
