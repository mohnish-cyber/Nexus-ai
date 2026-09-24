// The NEXUS orb: a canvas-rendered energy core that reacts to the assistant's state
// and to live audio levels. Pure Canvas 2D for performance; pauses when hidden.
import { useEffect, useRef } from "react";
import type { OrbState } from "../../types/events";

type RGB = [number, number, number];

const PALETTES: Record<OrbState, { a: RGB; b: RGB; energy: number; spin: number }> = {
  idle: { a: [56, 225, 255], b: [109, 124, 255], energy: 0.22, spin: 0.15 },
  listening: { a: [52, 245, 197], b: [56, 225, 255], energy: 0.45, spin: 0.3 },
  thinking: { a: [155, 123, 255], b: [56, 225, 255], energy: 0.62, spin: 0.9 },
  speaking: { a: [126, 249, 255], b: [155, 123, 255], energy: 0.5, spin: 0.35 },
  executing: { a: [255, 181, 71], b: [56, 225, 255], energy: 0.7, spin: 1.2 },
  waiting: { a: [255, 181, 71], b: [255, 122, 89], energy: 0.35, spin: 0.12 },
  completed: { a: [52, 211, 153], b: [56, 225, 255], energy: 0.4, spin: 0.3 },
  error: { a: [255, 84, 112], b: [255, 154, 60], energy: 0.75, spin: 0.2 },
};

interface Particle {
  r: number; // orbit radius factor
  angle: number;
  speed: number;
  size: number;
  tilt: number;
  phase: number;
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const mix = (a: RGB, b: RGB, t: number): RGB => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
const rgba = (c: RGB, alpha: number) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${alpha})`;

interface Props {
  state: OrbState;
  level?: number;
  size?: number;
  className?: string;
  onClick?: () => void;
  ariaLabel?: string;
}

export function NexusOrb({ state, level = 0, size = 320, className, onClick, ariaLabel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  const levelRef = useRef(level);
  stateRef.current = state;
  levelRef.current = level;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const count = reduced ? 40 : size > 200 ? 140 : 60;
    const particles: Particle[] = Array.from({ length: count }, () => ({
      r: 0.55 + Math.random() * 0.45,
      angle: Math.random() * Math.PI * 2,
      speed: (0.15 + Math.random() * 0.5) * (Math.random() < 0.5 ? -1 : 1),
      size: 0.4 + Math.random() * 1.4,
      tilt: (Math.random() - 0.5) * 0.9,
      phase: Math.random() * Math.PI * 2,
    }));

    let colorA: RGB = [...PALETTES.idle.a];
    let colorB: RGB = [...PALETTES.idle.b];
    let energy = PALETTES.idle.energy;
    let spin = PALETTES.idle.spin;
    let smoothLevel = 0;
    let flash = 0;
    let lastState: OrbState = stateRef.current;
    let raf = 0;
    let last = performance.now();
    let t = 0;

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000) * (reduced ? 0.35 : 1);
      last = now;
      t += dt;
      const st = stateRef.current;
      if (st !== lastState) {
        if (st === "completed" || st === "error") flash = 1;
        lastState = st;
      }
      const target = PALETTES[st];
      const k = Math.min(1, dt * 3.5);
      colorA = mix(colorA, target.a, k);
      colorB = mix(colorB, target.b, k);
      smoothLevel = lerp(smoothLevel, levelRef.current, Math.min(1, dt * 12));
      const audioBoost = st === "listening" || st === "speaking" ? smoothLevel : 0;
      energy = lerp(energy, target.energy + audioBoost * 0.6, k);
      spin = lerp(spin, target.spin, k);
      flash = Math.max(0, flash - dt * 1.4);

      const w = size;
      const cx = w / 2;
      const cy = w / 2;
      const base = w * 0.24;
      const breathe = Math.sin(t * (st === "waiting" ? 2.2 : 1.3)) * 0.035 + (st === "error" ? (Math.random() - 0.5) * 0.02 : 0);
      const R = base * (1 + breathe + energy * 0.1 + audioBoost * 0.18);

      ctx.clearRect(0, 0, w, w);
      ctx.globalCompositeOperation = "source-over";

      // Outer halo
      const halo = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * 2.1);
      halo.addColorStop(0, rgba(colorA, 0.2 + energy * 0.18));
      halo.addColorStop(0.45, rgba(colorB, 0.07 + energy * 0.06));
      halo.addColorStop(1, rgba(colorB, 0));
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 2.1, 0, Math.PI * 2);
      ctx.fill();

      ctx.globalCompositeOperation = "lighter";

      // Orbiting particles (behind + in front, faked with tilt)
      for (const p of particles) {
        p.angle += p.speed * dt * (0.6 + spin * 1.6 + audioBoost * 1.5);
        const orbit = R * (1.25 + p.r * 0.75 + (st === "listening" ? audioBoost * 0.5 : 0));
        const x = cx + Math.cos(p.angle) * orbit;
        const y = cy + Math.sin(p.angle) * orbit * (0.35 + Math.abs(p.tilt) * 0.5) + Math.sin(p.angle) * p.tilt * orbit * 0.4;
        const twinkle = 0.35 + 0.65 * Math.abs(Math.sin(t * 1.7 + p.phase));
        ctx.fillStyle = rgba(mix(colorA, colorB, (Math.sin(p.phase) + 1) / 2), 0.25 + twinkle * 0.45 * (0.5 + energy));
        ctx.beginPath();
        ctx.arc(x, y, p.size * (0.8 + energy * 0.6), 0, Math.PI * 2);
        ctx.fill();
      }

      // Tilted orbit rings
      ctx.lineWidth = 1;
      for (let i = 0; i < 3; i++) {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(t * spin * (i % 2 ? -0.35 : 0.25) + i * 1.1);
        ctx.strokeStyle = rgba(i === 1 ? colorB : colorA, 0.12 + energy * 0.14);
        ctx.beginPath();
        ctx.ellipse(0, 0, R * (1.55 + i * 0.22), R * (0.42 + i * 0.12), 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }

      // Executing: segmented progress ring
      if (st === "executing" || st === "thinking") {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(t * (st === "executing" ? 2.4 : 1.2));
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        const segs = st === "executing" ? 6 : 3;
        for (let i = 0; i < segs; i++) {
          const a0 = (i / segs) * Math.PI * 2;
          ctx.strokeStyle = rgba(colorA, 0.55);
          ctx.beginPath();
          ctx.arc(0, 0, R * 1.28, a0, a0 + (Math.PI * 2) / segs / 2.2);
          ctx.stroke();
        }
        ctx.restore();
      }

      // Core sphere
      const core = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.3, R * 0.05, cx, cy, R);
      core.addColorStop(0, rgba([240, 253, 255], 0.95));
      core.addColorStop(0.25, rgba(colorA, 0.85));
      core.addColorStop(0.7, rgba(colorB, 0.55));
      core.addColorStop(1, rgba(colorB, 0.05));
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, Math.PI * 2);
      ctx.fill();

      // Plasma filaments: sine-perturbed loops inside the core
      for (let j = 0; j < 4; j++) {
        ctx.strokeStyle = rgba(j % 2 ? colorA : [230, 250, 255], 0.16 + energy * 0.22);
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        const loops = 80;
        for (let i = 0; i <= loops; i++) {
          const a = (i / loops) * Math.PI * 2;
          const wobble =
            Math.sin(a * (3 + j) + t * (1.2 + j * 0.4) * (0.5 + spin)) * 0.12 * (0.4 + energy + audioBoost) +
            Math.sin(a * 7 - t * 2.1) * 0.03 * energy;
          const rr = R * (0.55 + j * 0.1 + wobble);
          const x = cx + Math.cos(a + t * 0.2 * (j + 1)) * rr;
          const y = cy + Math.sin(a + t * 0.2 * (j + 1)) * rr * (0.85 + 0.1 * Math.sin(t + j));
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // Speaking / listening: audio ripple rings
      if (audioBoost > 0.02) {
        for (let i = 0; i < 3; i++) {
          const phase = (t * 0.9 + i / 3) % 1;
          ctx.strokeStyle = rgba(colorA, (1 - phase) * 0.35 * Math.min(1, audioBoost * 2));
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(cx, cy, R * (1.05 + phase * 0.9), 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // Completion / error flash
      if (flash > 0) {
        ctx.strokeStyle = rgba(colorA, flash * 0.7);
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(cx, cy, R * (1 + (1 - flash) * 1.2), 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.globalCompositeOperation = "source-over";
      raf = requestAnimationFrame(draw);
    };

    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) {
        last = performance.now();
        raf = requestAnimationFrame(draw);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      role={onClick ? "button" : "img"}
      tabIndex={onClick ? 0 : undefined}
      aria-label={ariaLabel ?? `NEXUS is ${state}`}
      onClick={onClick}
      onKeyDown={(e) => {
        if (onClick && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onClick();
        }
      }}
      className={className}
      style={{ width: size, height: size, cursor: onClick ? "pointer" : "default" }}
    />
  );
}

export const ORB_STATE_TEXT: Record<OrbState, string> = {
  idle: "Standing by",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  executing: "Executing…",
  waiting: "Awaiting your approval",
  completed: "Completed",
  error: "Something needs attention",
};
