import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

// Must stay in step with LIVENESS_WEB_FRAMES / LIVENESS_WEB_FRAME_INTERVAL_MS
// in config.py. The interval is the part that matters: a blink lasts
// 100-400ms and has to span at least EYE_AR_CONSEC_FRAMES (2) captured
// frames, so sampling much slower than this drops fast blinks between frames
// and locks out real users.
const BURST_FRAMES = 20;
const BURST_INTERVAL_MS = 120;

export default function Login() {
  const [mode, setMode] = useState("pin"); // "pin" | "face"
  const [userId, setUserId] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  // Set after a PIN login on a 2FA-enabled account: {challenge_token, name}.
  const [twoFa, setTwoFa] = useState(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const { login, loginWithFace, verifyTwoFactor } = useAuth();
  const navigate = useNavigate();

  // Start/stop the webcam when switching modes (or entering the 2FA
  // verification step), and always release it when leaving the page.
  useEffect(() => {
    setError("");
    setInfo("");
    if (mode !== "face" && !twoFa) {
      stopCamera();
      return;
    }
    let cancelled = false;
    setCameraReady(false);
    navigator.mediaDevices
      .getUserMedia({ video: { width: 640, height: 480 } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraReady(true);
      })
      .catch(() => {
        setError("Could not access the camera. Allow camera permission and try again.");
      });
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [mode, twoFa]);

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setCameraReady(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(userId, pin);
      if (data.requires_2fa) {
        // PIN accepted, but adaptive auth wants a Face ID second factor for
        // this session. Carry the risk band + reasons so we can explain why.
        setTwoFa({
          challenge_token: data.challenge_token,
          name: data.name,
          risk_band: data.risk_band,
          reasons: data.reasons || [],
        });
        return;
      }
      navigate("/dashboard");
    } catch (err) {
      if (err.response?.status === 401) {
        setError("Invalid user ID or PIN.");
      } else {
        setError("Cannot reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  }

  function captureFrame() {
    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.9);
  }

  // Capture a short burst so the server can look for a blink across it. One
  // snapshot can never show a blink, which is what let a photograph pass.
  // Quality is a little lower than the single-frame path: 20 frames at 0.9
  // would be ~2.4MB per attempt, and the frames only need to be good enough
  // for eye landmarks plus one recognition pass.
  function captureBurst(onProgress) {
    return new Promise((resolve) => {
      const video = videoRef.current;
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext("2d");
      const frames = [];

      const grab = () => {
        ctx.drawImage(video, 0, 0);
        frames.push(canvas.toDataURL("image/jpeg", 0.8));
        if (onProgress) onProgress(frames.length, BURST_FRAMES);
        if (frames.length >= BURST_FRAMES) resolve(frames);
        else setTimeout(grab, BURST_INTERVAL_MS);
      };
      grab();
    });
  }

  async function handleTwoFaScan() {
    if (!videoRef.current || !cameraReady) return;
    setError("");
    setLoading(true);
    try {
      const frames = await captureBurst((n, total) =>
        setInfo(`Blink once — capturing ${n}/${total}…`)
      );
      setInfo("Verifying it's you…");
      const data = await verifyTwoFactor(twoFa.challenge_token, frames);
      setInfo(`Welcome back, ${data.name}!`);
      stopCamera();
      navigate("/dashboard");
    } catch (err) {
      setInfo("");
      if (err.response?.status === 401) {
        const detail = err.response.data?.detail || "";
        if (detail.includes("expired")) {
          setError("The 2FA window expired — sign in with your PIN again.");
          setTwoFa(null);
        } else {
          setError(detail || "Face verification failed. Try again.");
        }
      } else {
        setError("Cannot reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleFaceScan() {
    if (!videoRef.current || !cameraReady) return;
    setError("");
    setLoading(true);
    try {
      const frames = await captureBurst((n, total) =>
        setInfo(`Blink once — capturing ${n}/${total}…`)
      );
      setInfo("Matching your face…");
      const data = await loginWithFace(frames);
      setInfo(`Welcome back, ${data.name}!`);
      stopCamera();
      navigate("/dashboard");
    } catch (err) {
      setInfo("");
      if (err.response?.status === 401) {
        setError(err.response.data?.detail || "Face not recognized. Try again.");
      } else if (err.response?.status === 503) {
        setError("Face login is not set up on the server (no enrolled faces).");
      } else {
        setError("Cannot reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="centered-page">
      <div className="card login-card">
        <div className="login-logo">🏦</div>
        <h1 className="login-title">SmartBank</h1>
        <p className="login-subtitle">Secure Online Banking Portal</p>

        {!twoFa && (
          <div className="login-tabs">
            <button
              type="button"
              className={`login-tab ${mode === "pin" ? "active" : ""}`}
              onClick={() => setMode("pin")}
            >
              🔑 User ID + PIN
            </button>
            <button
              type="button"
              className={`login-tab ${mode === "face" ? "active" : ""}`}
              onClick={() => setMode("face")}
            >
              👤 Face ID
            </button>
          </div>
        )}

        {twoFa ? (
          <div>
            <p className="success-text" style={{ marginTop: 0 }}>
              {twoFa.risk_band === "high"
                ? "PIN accepted — but this sign-in looks higher-risk, so we need a clear Face ID match to be sure it's you."
                : "PIN accepted. For extra security on this sign-in, verify it's you with Face ID."}
            </p>
            {twoFa.reasons && twoFa.reasons.length > 0 && (
              <div className="risk-reasons">
                <span className="risk-reasons-label">
                  Why the extra check:
                </span>
                <ul className="risk-reasons-list">
                  {twoFa.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="face-video-wrap">
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video ref={videoRef} autoPlay playsInline muted />
              {!cameraReady && !error && (
                <div className="face-video-placeholder">Starting camera…</div>
              )}
            </div>

            {/* The server rejects a face it never saw blink, so say so before
                they press the button rather than after it fails. */}
            <p className="field-label" style={{ marginTop: 8 }}>
              Look at the camera and blink once while it captures — a
              photograph won't get in.
            </p>

            {error && <p className="error-text">{error}</p>}
            {info && <p className="success-text">{info}</p>}

            <button
              className="btn btn-primary"
              type="button"
              onClick={handleTwoFaScan}
              disabled={loading || !cameraReady}
              style={{ width: "100%" }}
            >
              {loading ? "Hold still and blink…" : "👁️ Blink to Verify"}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => { setTwoFa(null); setError(""); setInfo(""); }}
              disabled={loading}
              style={{ width: "100%", marginTop: 8 }}
            >
              Cancel
            </button>
          </div>
        ) : mode === "pin" ? (
          <form onSubmit={handleSubmit}>
            <label className="field-label">User ID</label>
            <input
              className="input"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="USR001"
              required
            />

            <label className="field-label">PIN</label>
            <input
              className="input"
              type="password"
              inputMode="numeric"
              maxLength={4}
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              required
            />

            {error && <p className="error-text">{error}</p>}

            <button
              className="btn btn-primary"
              type="submit"
              disabled={loading}
              style={{ width: "100%" }}
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
        ) : (
          <div>
            <div className="face-video-wrap">
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video ref={videoRef} autoPlay playsInline muted />
              {!cameraReady && !error && (
                <div className="face-video-placeholder">Starting camera…</div>
              )}
            </div>

            {error && <p className="error-text">{error}</p>}
            {info && <p className="success-text">{info}</p>}

            <button
              className="btn btn-primary"
              type="button"
              onClick={handleFaceScan}
              disabled={loading || !cameraReady}
              style={{ width: "100%" }}
            >
              {loading ? "Hold still and blink…" : "👁️ Blink to Sign In"}
            </button>
            <p className="login-hint">
              Look straight at the camera in good light and blink once while it
              captures. A photograph won't get in.
            </p>
          </div>
        )}

        {mode === "pin" && !twoFa && (
          <p className="login-hint">
            Use the User ID and PIN created during ATM enrollment.
          </p>
        )}
      </div>
    </div>
  );
}
