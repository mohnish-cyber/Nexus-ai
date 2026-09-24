// One-shot, user-initiated screen capture via the browser's screen-sharing prompt.
// Nothing is recorded continuously: one frame is grabbed and the share stops immediately.

export function screenCaptureSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;
}

export async function captureScreenFrame(): Promise<File> {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  try {
    const video = document.createElement("video");
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    await new Promise((r) => setTimeout(r, 250)); // let the first real frame arrive
    const scale = Math.min(1, 1920 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Capture failed"))), "image/png"),
    );
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    return new File([blob], `screen-${stamp}.png`, { type: "image/png" });
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}
