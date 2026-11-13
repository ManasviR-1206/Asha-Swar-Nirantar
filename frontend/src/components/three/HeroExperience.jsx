import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  ContactShadows,
  Sparkles,
  RoundedBox,
  Line,
  Text,
  MeshReflectorMaterial,
  SpotLight,
} from "@react-three/drei";
import { EffectComposer, Bloom, DepthOfField, Vignette } from "@react-three/postprocessing";
import * as THREE from "three";
import AshaWorker from "./AshaWorker.jsx";
import Tara from "./Tara.jsx";

/**
 * THE IMMERSIVE HERO WORLD - cinematic 3D environment
 *
 * Composition:
 *  - Left foreground: headline (2D overlay, in Landing.jsx) - never covered.
 *  - Right of centre: large full-body ASHA worker + Tara floating above her shoulder.
 *  - Around them: floating holographic panels (Voice Visits / Pulse Thread),
 *    volumetric light shafts, animated floor rings, distant data pillars,
 *    reflective floor, dust particles, depth of field, controlled bloom.
 *
 * Signature timeline (seconds from scene start):
 *  0.0-2.2  particles assemble into the holographic QR
 *  2.2-3.6  QR hovers, shimmers, leans in 3D
 *  3.6-5.6  modules detach, swirl outward along curved paths
 *  5.6-8.2  particles converge into the ASHA worker silhouette
 *  8.2-9.8  silhouette materializes into the 3D character + holo rings
 *  9.8-11.4 Tara floats in beside her, waves; panels fade up
 *  after    interactive idle: camera drift, pointer parallax, blinking
 */

const GRID = 26;
const PINK = "#f078ad";
const HOT = "#e84d9b";
const LAV = "#bba6ff";
const VIOLET = "#8755d9";
const PEARL = "#fff7fc";

/* Character placement (world units) */
const WORKER_X = 0.85; // slightly right of centre
const WORKER_SCALE = 1.3; // large, prominent
const TARA_X = 2.15; // beside the worker
const TARA_Y = 1.7; // above her shoulder level

const EASE = {
  inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
  outCubic: (x) => 1 - Math.pow(1 - x, 3),
  outBack: (x) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
  },
};

function buildQRPattern(n) {
  // Real QR-like matrix: three finder patterns, timing lines, data modules.
  const zones = [
    [0, 0],
    [0, n - 7],
    [n - 7, 0],
  ];
  const grid = new Array(n * n).fill(false);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (r === 0 || c === 0 || r === n - 1 || c === n - 1) continue; // quiet zone
      const zone = zones.find(
        ([zr, zc]) => r >= zr && r < zr + 7 && c >= zc && c < zc + 7
      );
      if (zone) {
        const [zr, zc] = zone;
        const ring = Math.max(Math.abs(r - zr - 3), Math.abs(c - zc - 3));
        grid[r * n + c] = ring === 3 || ring <= 1;
      } else if (r === 6 || c === 6) {
        grid[r * n + c] = (r + c) % 2 === 0;
      } else {
        grid[r * n + c] = Math.random() < 0.42;
      }
    }
  }
  return grid;
}

function sampleSilhouette(count) {
  // Points inside a stylised female figure (saree silhouette), in metres.
  const inside = (x, y) => {
    const ax = Math.abs(x);
    if (Math.hypot(x, y - 1.62) < 0.13) return true; // head
    if (ax < 0.05 && y > 1.42 && y < 1.52) return true; // neck
    if (y > 1.02 && y <= 1.42 && ax < 0.24) return true; // torso
    if (y > 0.78 && y <= 1.32 && ax > 0.2 && ax < 0.31) return true; // arms
    if (y > 0.06 && y <= 1.02) {
      const hw = 0.22 + (1.02 - y) * 0.3; // saree flare
      if (ax < hw) return true;
    }
    return false;
  };
  const pts = [];
  let guard = 0;
  while (pts.length < count && guard < count * 80) {
    guard++;
    const x = (Math.random() - 0.5) * 1.1;
    const y = Math.random() * 1.8;
    if (inside(x, y)) {
      pts.push(new THREE.Vector3(x, y, (Math.random() - 0.5) * 0.16));
    }
  }
  return pts;
}

/* window-level pointer so the scene responds even under HTML overlays */
function useWindowPointer() {
  const ref = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const onMove = (e) => {
      ref.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      ref.current.y = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    window.addEventListener("pointermove", onMove);
    return () => window.removeEventListener("pointermove", onMove);
  }, []);
  return ref;
}

/* soft radial glow sprite (fake volumetric haze) */
function useGlowTexture() {
  return useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, "rgba(240,120,173,0.5)");
    grd.addColorStop(0.45, "rgba(135,85,217,0.22)");
    grd.addColorStop(1, "rgba(16,12,24,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(c);
  }, []);
}

function GlowBackdrop() {
  const tex = useGlowTexture();
  const common = {
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    blending: THREE.AdditiveBlending,
  };
  return (
    <>
      {/* main haze behind the characters */}
      <mesh position={[WORKER_X, 1.9, -3.2]}>
        <planeGeometry args={[9, 9]} />
        <meshBasicMaterial map={tex} opacity={0.5} {...common} />
      </mesh>
      {/* secondary violet haze, background left */}
      <mesh position={[-3.8, 2.8, -5.5]}>
        <planeGeometry args={[5.5, 5.5]} />
        <meshBasicMaterial map={tex} opacity={0.32} {...common} />
      </mesh>
      {/* tertiary glow far right */}
      <mesh position={[4.8, 2.4, -6.5]}>
        <planeGeometry args={[4.5, 4.5]} />
        <meshBasicMaterial map={tex} opacity={0.26} {...common} />
      </mesh>
    </>
  );
}

/* distant glowing data pillars - background layer */
function Pillars() {
  const pillars = useMemo(
    () => [
      { x: -6.4, h: 5.6, w: 0.34, c: VIOLET, z: -7.5 },
      { x: -4.7, h: 3.4, w: 0.22, c: HOT, z: -9.5 },
      { x: 5.6, h: 4.8, w: 0.3, c: PINK, z: -8.5 },
      { x: 7.3, h: 6.4, w: 0.42, c: VIOLET, z: -6.5 },
      { x: 4.2, h: 2.6, w: 0.18, c: LAV, z: -10.5 },
      { x: -7.8, h: 4.2, w: 0.26, c: PINK, z: -6.0 },
    ],
    []
  );
  return pillars.map((p, i) => (
    <group key={i} position={[p.x, p.h / 2, p.z]}>
      <mesh>
        <boxGeometry args={[p.w, p.h, p.w]} />
        <meshBasicMaterial
          color={p.c}
          transparent
          opacity={0.32}
          toneMapped={false}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      {/* brighter core */}
      <mesh>
        <boxGeometry args={[p.w * 0.3, p.h * 0.92, p.w * 0.3]} />
        <meshBasicMaterial
          color={PEARL}
          transparent
          opacity={0.5}
          toneMapped={false}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
    </group>
  ));
}

/* animated holographic rings circling the worker's base */
function FloorRings() {
  const r1 = useRef();
  const r2 = useRef();
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (r1.current) {
      r1.current.rotation.z = t * 0.25;
      r1.current.material.opacity = 0.3 + Math.sin(t * 1.2) * 0.09;
    }
    if (r2.current) {
      r2.current.rotation.z = -t * 0.18;
      r2.current.material.opacity = 0.22 + Math.cos(t * 0.9) * 0.07;
    }
  });
  return (
    <group position={[0, 0.02, 0]}>
      <mesh ref={r1} rotation={[-Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.05, 0.008, 8, 72]} />
        <meshBasicMaterial color={HOT} transparent opacity={0.3} toneMapped={false} />
      </mesh>
      <mesh ref={r2} rotation={[-Math.PI / 2, 0.35, 0]}>
        <torusGeometry args={[1.38, 0.006, 8, 72]} />
        <meshBasicMaterial color={LAV} transparent opacity={0.22} toneMapped={false} />
      </mesh>
    </group>
  );
}

/* translucent holographic glass body */
function GlassPanel({ w = 2, h = 2.5, glow = PINK }) {
  return (
    <group>
      <RoundedBox args={[w + 0.07, h + 0.07, 0.03]} radius={0.07} smoothness={4}>
        <meshBasicMaterial color={glow} transparent opacity={0.3} toneMapped={false} />
      </RoundedBox>
      <RoundedBox args={[w, h, 0.055]} radius={0.06} smoothness={4}>
        <meshPhysicalMaterial
          color="#2a1633"
          transparent
          opacity={0.58}
          roughness={0.16}
          metalness={0.3}
          clearcoat={0.85}
          clearcoatRoughness={0.2}
          emissive="#38152e"
          emissiveIntensity={0.4}
        />
      </RoundedBox>
      <mesh position={[0, 0, 0.03]}>
        <planeGeometry args={[w - 0.1, h - 0.1]} />
        <meshBasicMaterial color="#bba6ff" transparent opacity={0.05} toneMapped={false} />
      </mesh>
    </group>
  );
}

/* LEFT PANEL - Voice Visits: live waveform + recording status */
function VoicePanel({ position, rotation, scale = 1 }) {
  const bars = useRef([]);
  const recDot = useRef();
  const phases = useMemo(
    () => Array.from({ length: 14 }, (_, i) => i * 0.53 + Math.random() * 1.2),
    []
  );

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    bars.current.forEach((b, i) => {
      if (!b) return;
      b.scale.y = 0.25 + Math.abs(Math.sin(t * 5.2 + phases[i])) * 1.25;
    });
    if (recDot.current) {
      recDot.current.material.opacity =
        Math.sin(t * 3.2) > 0 ? 1 : 0.25;
    }
  });

  return (
    <group position={position} rotation={rotation} scale={scale}>
      <GlassPanel w={1.5} h={1.05} glow={PINK} />

      {/* header: rec dot + title + LIVE badge */}
      <group position={[0, 0.36, 0.045]}>
        <mesh ref={recDot} position={[-0.62, 0, 0]}>
          <sphereGeometry args={[0.024, 10, 10]} />
          <meshBasicMaterial color={HOT} toneMapped={false} transparent />
        </mesh>
        <Text fontSize={0.072} color={PINK} anchorX="left" anchorY="middle" position={[-0.54, 0, 0]} letterSpacing={0.12}>
          VOICE VISITS
        </Text>
        <Text fontSize={0.05} color={PEARL} anchorX="right" anchorY="middle" position={[0.66, 0, 0]}>
          LIVE
        </Text>
      </group>

      {/* animated waveform */}
      <group position={[0, 0.02, 0.045]}>
        {phases.map((_, i) => {
          const x = -0.63 + i * 0.097;
          return (
            <mesh
              key={i}
              ref={(el) => (bars.current[i] = el)}
              position={[x, 0, 0]}
              scale={[1, 0.5, 1]}
            >
              <boxGeometry args={[0.03, 0.34, 0.01]} />
              <meshBasicMaterial color={i % 3 === 1 ? LAV : PINK} toneMapped={false} />
            </mesh>
          );
        })}
      </group>

      {/* footer: REC timer + progress */}
      <group position={[0, -0.36, 0.045]}>
        <Text fontSize={0.055} color="#c7b8c9" anchorX="left" anchorY="middle" position={[-0.66, 0, 0]}>
          REC 00:42
        </Text>
        <mesh position={[0.18, 0, 0]}>
          <boxGeometry args={[0.72, 0.006, 0.004]} />
          <meshBasicMaterial color={VIOLET} transparent opacity={0.5} toneMapped={false} />
        </mesh>
        <mesh position={[-0.18 + 0.198, 0, 0.001]}>
          <boxGeometry args={[0.36, 0.006, 0.005]} />
          <meshBasicMaterial color={PINK} toneMapped={false} />
        </mesh>
      </group>
    </group>
  );
}

/* RIGHT PANEL - Pulse Thread: miniature connected health timeline */
function PulseThreadPanel({ position, rotation, scale = 1 }) {
  const nodes = [
    { y: 0.4, c: PINK, label: "ANC 28W" },
    { y: 0.08, c: LAV, label: "HB 11.2" },
    { y: -0.24, c: PINK, label: "WT 53KG" },
    { y: -0.56, c: LAV, label: "VAX 2" },
  ];
  const pulse = useRef();
  useFrame((state) => {
    if (!pulse.current) return;
    const u = (state.clock.elapsedTime * 0.25) % 1;
    pulse.current.position.y = THREE.MathUtils.lerp(0.4, -0.56, u);
  });

  return (
    <group position={position} rotation={rotation} scale={scale}>
      <GlassPanel w={1.05} h={1.4} glow={LAV} />

      <group position={[0, 0.56, 0.045]}>
        <Text fontSize={0.07} color={LAV} anchorX="center" anchorY="middle" letterSpacing={0.12}>
          PULSE THREAD
        </Text>
      </group>

      {/* vertical thread */}
      <mesh position={[-0.3, -0.08, 0.045]}>
        <cylinderGeometry args={[0.006, 0.006, 1.0, 6]} />
        <meshBasicMaterial color={PINK} transparent opacity={0.55} toneMapped={false} />
      </mesh>

      {/* connected nodes */}
      {nodes.map((n) => (
        <group key={n.label} position={[0, n.y, 0.045]}>
          <mesh position={[-0.3, 0, 0]}>
            <sphereGeometry args={[0.032, 12, 12]} />
            <meshBasicMaterial color={n.c} toneMapped={false} />
          </mesh>
          <Text fontSize={0.062} color={PEARL} anchorX="left" anchorY="middle" position={[-0.2, 0, 0]} letterSpacing={0.06}>
            {n.label}
          </Text>
        </group>
      ))}

      {/* travelling data pulse */}
      <mesh ref={pulse} position={[-0.3, 0.4, 0.055]}>
        <sphereGeometry args={[0.02, 10, 10]} />
        <meshBasicMaterial color={PEARL} toneMapped={false} />
      </mesh>

      <Text fontSize={0.05} color="#c7b8c9" anchorX="center" anchorY="middle" position={[0, -0.62, 0.045]}>
        Connected histories
      </Text>
    </group>
  );
}

/* glowing connection line between the worker and a panel */
function ConnectionBeam({ from, to, color, opacity = 1, activeRef = null }) {
  const pulse = useRef();
  const group = useRef();
  const dir = useMemo(() => new THREE.Vector3(...to).sub(new THREE.Vector3(...from)), [from, to]);
  useFrame((state) => {
    if (!pulse.current) return;
    const u = (state.clock.elapsedTime * 0.18) % 1;
    pulse.current.position.set(
      from[0] + dir.x * u,
      from[1] + dir.y * u,
      from[2] + dir.z * u
    );
    const s = Math.sin(u * Math.PI);
    pulse.current.scale.setScalar(0.5 + s);
  });
  useFrame(() => {
    if (!group.current || !activeRef) return;
    group.current.visible = activeRef.current > 10.6;
  });
  return (
    <group ref={group} visible={false}>
      <Line points={[from, to]} color={color} lineWidth={1.2} transparent opacity={0.32 * opacity} />
      <mesh ref={pulse}>
        <sphereGeometry args={[0.028, 8, 8]} />
        <meshBasicMaterial color={PEARL} toneMapped={false} transparent opacity={opacity} />
      </mesh>
    </group>
  );
}

/* ====================== main scene ====================== */

export default function HeroExperience({ replayKey = 0 }) {
  return (
    <Canvas
      camera={{ position: [0, 1.5, 7.2], fov: 42 }}
      dpr={[1, 1.6]}
      gl={{ antialias: true, alpha: true }}
      style={{ background: "transparent" }}
    >
      <fog attach="fog" args={["#100C18", 10, 22]} />
      <CameraRig />
      <SceneContent />
      <EffectComposer multisampling={0}>
        <DepthOfField target={[WORKER_X, 1.5, 0]} focalLength={0.35} bokehScale={2.2} height={480} />
        {/* Threshold raised so the newly-lit face does not bloom into a
            washed-out blob; the holograms and neon stay above it. */}
        <Bloom mipmapBlur intensity={0.62} luminanceThreshold={0.78} luminanceSmoothing={0.26} radius={0.7} />
        <Vignette offset={0.28} darkness={0.62} />
      </EffectComposer>
    </Canvas>
  );
}

/** Smooth camera: responsive framing + gentle drift + pointer parallax */
function CameraRig() {
  const { camera, size } = useThree();
  const pointer = useWindowPointer();
  const reduced = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  /* A very soft warm fill that rides with the camera. It guarantees the
   * worker's face stays readable wherever the camera drifts, without
   * flattening the scene (the intensity is deliberately low). */
  const cameraFill = useMemo(() => {
    const light = new THREE.PointLight("#ffe6cd", 0.65, 16, 1.4);
    light.position.set(0.4, 1.1, 1.2);
    return light;
  }, []);

  useEffect(() => {
    camera.add(cameraFill);
    return () => {
      camera.remove(cameraFill);
    };
  }, [camera, cameraFill]);

  useFrame((state, delta) => {
    const aspect = size.width / size.height;
    const zBase = aspect < 0.85 ? 10.6 : aspect < 1.25 ? 8.6 : 7.2;
    const yBase = aspect < 0.85 ? 1.7 : 1.5;
    const t = state.clock.elapsedTime;

    const driftX = reduced ? 0 : Math.sin(t * 0.22) * 0.16 + pointer.current.x * 0.38;
    const driftY = reduced ? 0 : Math.sin(t * 0.34) * 0.07 + pointer.current.y * 0.2;

    camera.position.x = THREE.MathUtils.damp(camera.position.x, driftX, 2.2, delta);
    camera.position.y = THREE.MathUtils.damp(camera.position.y, yBase + driftY, 2.2, delta);
    camera.position.z = THREE.MathUtils.damp(camera.position.z, zBase, 2.2, delta);
    camera.lookAt(0, aspect < 0.85 ? 1.7 : 1.35, 0);
  });
  return null;
}

function SceneContent() {
  const { size } = useThree();
  const [taraState, setTaraState] = useState("wave");
  const taraFlipped = useRef(false);
  const startRef = useRef(null);
  const pointer = useWindowPointer();
  const reduced = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    []
  );

  /* responsive holographic panel layout */
  const layout = useMemo(() => {
    const aspect = size.width / size.height;
    if (aspect < 0.85)
      return {
        voice: [-1.95, 3.75, -0.9],
        pulse: [1.95, 3.75, -0.9],
        voiceRot: 0.34,
        pulseRot: -0.34,
        panelScale: 0.5,
      };
    if (aspect < 1.25)
      return {
        voice: [-2.75, 3.35, -0.5],
        pulse: [3.35, 3.0, -0.5],
        voiceRot: 0.42,
        pulseRot: -0.42,
        panelScale: 0.62,
      };
    return {
      voice: [-2.85, 3.05, -0.5],
      pulse: [3.3, 2.85, -0.6],
      voiceRot: 0.48,
      pulseRot: -0.48,
      panelScale: 0.72,
    };
  }, [size]);

  const scene = useMemo(() => {
    const grid = buildQRPattern(GRID);
    const cell = 0.072;
    const filled = [];
    for (let r = 0; r < GRID; r++) {
      for (let c = 0; c < GRID; c++) {
        if (grid[r * GRID + c]) {
          // QR hovers in mid-air where the worker will form (relative coords)
          filled.push([(c - GRID / 2) * cell, 1.5 - (r - GRID / 2) * cell, 0]);
        }
      }
    }
    const N = filled.length;

    const qrPos = new Float32Array(N * 3);
    filled.forEach((p, i) => qrPos.set(p, i * 3));

    // silhouette scaled up to match the final character size
    const workerPos = new Float32Array(N * 3);
    sampleSilhouette(N).forEach((p, i) =>
      workerPos.set([p.x * WORKER_SCALE, p.y * WORKER_SCALE, p.z], i * 3)
    );

    const startPos = new Float32Array(N * 3);
    const scatterPos = new Float32Array(N * 3);
    const arcDir = new Float32Array(N * 2);
    const phaseOffset = new Float32Array(N);
    const rotSpeed = new Float32Array(N);
    const colorSeed = new Float32Array(N);

    const sv = new THREE.Vector3();
    const sc = new THREE.Vector3();
    for (let i = 0; i < N; i++) {
      sv.randomDirection().multiplyScalar(2.6 + Math.random() * 1.5);
      startPos[i * 3] = sv.x;
      startPos[i * 3 + 1] = sv.y * 0.6 + 1.5;
      startPos[i * 3 + 2] = sv.z;

      sc.randomDirection().multiplyScalar(1.2 + Math.random() * 1.7);
      scatterPos[i * 3] = sc.x * 1.5;
      scatterPos[i * 3 + 1] = Math.abs(sc.y) * 0.9 + 0.8;
      scatterPos[i * 3 + 2] = sc.z * 0.9;

      arcDir[i * 2] = Math.random() - 0.5;
      arcDir[i * 2 + 1] = Math.random() - 0.5;
      phaseOffset[i] = Math.random() * Math.PI * 2;
      rotSpeed[i] = (Math.random() - 0.5) * 1.6;
      colorSeed[i] = Math.random();
    }

    return { N, qrPos, workerPos, startPos, scatterPos, arcDir, phaseOffset, rotSpeed, colorSeed };
  }, []);

  const squaresRef = useRef();
  const group = useRef();
  const workerGroup = useRef();
  const taraGroup = useRef();
  const voicePanel = useRef();
  const pulsePanel = useRef();
  const holoRing = useRef();
  const holoRing2 = useRef();
  const tRef = useRef(0);

  const dummy = useMemo(() => new THREE.Object3D(), []);
  /* drei's SpotLight requires a real Object3D as its target (not an array) */
  const lightTarget = useMemo(() => {
    const o = new THREE.Object3D();
    o.position.set(WORKER_X, 1.2, 0);
    return o;
  }, []);
  /* Target for the worker's face key light — her head sits at
     y = 1.56 * WORKER_SCALE inside the worker group. */
  const faceTarget = useMemo(() => {
    const o = new THREE.Object3D();
    o.position.set(0, 1.52, 0);
    return o;
  }, []);
  const colorTmp = useMemo(() => new THREE.Color(), []);
  const pink = useMemo(() => new THREE.Color(PINK), []);
  const pearl = useMemo(() => new THREE.Color(PEARL), []);
  const lav = useMemo(() => new THREE.Color(LAV), []);
  const bgFade = useMemo(() => new THREE.Color("#241226"), []);

  useFrame((r3fState) => {
    if (startRef.current === null) {
      startRef.current = reduced ? r3fState.clock.elapsedTime - 60 : r3fState.clock.elapsedTime;
    }
    const t = r3fState.clock.elapsedTime - startRef.current;
    tRef.current = t;

    const { N, qrPos, workerPos, startPos, scatterPos, arcDir, phaseOffset, rotSpeed, colorSeed } = scene;
    const mesh = squaresRef.current;
    if (!mesh) return;

    const seg = (a, b) => THREE.MathUtils.clamp((t - a) / (b - a), 0, 1);
    const pAssemble = EASE.outCubic(seg(0, 2.2));
    const hoverT = seg(2.2, 3.6);
    const pScatter = EASE.inOut(seg(3.6, 5.6));
    const pForm = EASE.inOut(seg(5.6, 8.2));
    const pMat = seg(8.2, 9.8);
    const pTara = EASE.outBack(seg(9.8, 10.6));
    const pPanels = EASE.outCubic(seg(10.2, 11.8));
    const auraP = EASE.inOut(seg(8.2, 10.0));

    /* group sway: QR hologram leans while floating, then gentle pointer parallax */
    if (group.current) {
      const lean = Math.sin(t * 1.6) * 0.22 * (1 - pScatter) * (1 - pScatter);
      group.current.rotation.y = lean * (1 - pForm) + pointer.current.x * 0.09 * pForm;
      group.current.rotation.x = -0.14 * (1 - pForm) + pointer.current.y * 0.04 * pForm;
    }

    for (let i = 0; i < N; i++) {
      const i3 = i * 3;
      const seed = colorSeed[i];
      const phaseOffsetI = phaseOffset[i];

      let x, y, z, scale;

      if (t < 3.6) {
        // assemble into the QR + hover shimmer
        const hov = hoverT * (1 - hoverT) * 4;
        const float = Math.sin(t * 2.2 + phaseOffsetI) * 0.02 * hov;
        x = startPos[i3] + (qrPos[i3] - startPos[i3]) * pAssemble;
        y = startPos[i3 + 1] + (qrPos[i3 + 1] - startPos[i3 + 1]) * pAssemble + float;
        z = startPos[i3 + 2] + (qrPos[i3 + 2] - startPos[i3 + 2]) * pAssemble;
        scale = 0.9 + 0.1 * pAssemble;
        const shimmer = 0.75 + 0.25 * Math.sin(t * 3 + phaseOffsetI * 3);
        colorTmp.copy(pink).lerp(pearl, seed * 0.75);
        if (seed > 0.82) colorTmp.copy(lav);
        colorTmp.multiplyScalar(shimmer);
      } else if (t < 5.6) {
        // scatter outward with swirl
        const p = pScatter;
        const ang = p * (1.2 + seed) * Math.PI;
        const rx0 = qrPos[i3] + (scatterPos[i3] - qrPos[i3]) * p;
        const ry0 = qrPos[i3 + 1] + (scatterPos[i3 + 1] - qrPos[i3 + 1]) * p;
        const rz0 = qrPos[i3 + 2] + (scatterPos[i3 + 2] - qrPos[i3 + 2]) * p;
        x = rx0 * Math.cos(ang) - rz0 * Math.sin(ang);
        y = ry0;
        z = rx0 * Math.sin(ang) + rz0 * Math.cos(ang);
        scale = 0.9 - 0.25 * p;
        colorTmp.copy(pink).lerp(lav, p * 0.7).lerp(pearl, seed * 0.3);
      } else if (t < 8.2) {
        // converge into the silhouette along curved paths
        const p = pForm;
        const bump = Math.sin(p * Math.PI) * 0.55;
        x = scatterPos[i3] + (workerPos[i3] - scatterPos[i3]) * p + arcDir[i3] * bump;
        y = scatterPos[i3 + 1] + (workerPos[i3 + 1] - scatterPos[i3 + 1]) * p;
        z =
          scatterPos[i3 + 2] +
          (workerPos[i3 + 2] - scatterPos[i3 + 2]) * p +
          arcDir[i3 + 1] * bump * 0.5;
        const jig = 1 - p < 0.08 ? Math.sin(t * 30 + phaseOffsetI) * 0.004 : 0;
        y += jig;
        scale = 0.65 + 0.15 * p;
        colorTmp.copy(lav).lerp(pink, p).lerp(pearl, seed * 0.35);
      } else {
        // soft expanding aura that fades back into the scene
        const floatY = Math.sin(t * 1.4 + phaseOffsetI) * 0.03;
        x = workerPos[i3] * (1 + auraP * 0.55);
        y = workerPos[i3 + 1] * (1 + auraP * 0.28) + 0.18 * auraP + floatY;
        z = workerPos[i3 + 2] * (1 + auraP * 1.4);
        scale = Math.max(0.12, 0.8 - auraP * 0.65);
        colorTmp.copy(pink).lerp(bgFade, auraP * 0.85);
      }

      dummy.position.set(x, y, z);
      dummy.rotation.set(t * rotSpeed[i], t * rotSpeed[i] * 0.7, phaseOffsetI);
      dummy.scale.setScalar(scale * 0.058 + 0.012);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
      mesh.setColorAt(i, colorTmp);
    }

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;

    /* worker materialization at full size */
    if (workerGroup.current) {
      const appear = pMat;
      const s = (EASE.outBack(appear) * 0.25 + appear * 0.75) * WORKER_SCALE;
      workerGroup.current.scale.setScalar(Math.max(0.001, s));
      workerGroup.current.position.y = -0.3 * (1 - EASE.outCubic(appear));
      workerGroup.current.rotation.y = -0.5 * (1 - EASE.outCubic(appear));
      workerGroup.current.visible = appear > 0.01;
    }

    /* holographic welcome rings */
    if (holoRing.current) {
      const rp = seg(8.6, 10.2);
      holoRing.current.visible = rp > 0.02 && rp < 0.999;
      holoRing.current.scale.setScalar(0.3 + EASE.outCubic(rp) * 1.25);
      holoRing.current.material.opacity = 0.55 * Math.sin(rp * Math.PI);
      holoRing.current.rotation.z = t * 0.4;
    }
    if (holoRing2.current) {
      const rp = seg(9.0, 11.0);
      holoRing2.current.visible = rp > 0.02 && rp < 0.999;
      holoRing2.current.scale.setScalar(0.2 + EASE.outCubic(rp) * 1.1);
      holoRing2.current.material.opacity = 0.35 * Math.sin(rp * Math.PI);
      holoRing2.current.rotation.z = -t * 0.3;
    }

    /* Tara floats in beside her, above shoulder level */
    if (taraGroup.current) {
      taraGroup.current.scale.setScalar(Math.max(0.001, pTara));
      taraGroup.current.position.x = TARA_X - WORKER_X + (1 - EASE.outCubic(seg(9.8, 10.6))) * 0.9;
      taraGroup.current.position.y = TARA_Y;
      taraGroup.current.visible = pTara > 0.01;
      if (t > 11.2 && !taraFlipped.current) {
        taraFlipped.current = true;
        setTaraState("idle");
      }
    }

    /* holographic panels float in */
    const panelFloat = Math.sin(t * 0.8) * 0.05;
    if (voicePanel.current) {
      voicePanel.current.scale.setScalar(Math.max(0.001, layout.panelScale * (pPanels || 0)));
      voicePanel.current.position.set(
        layout.voice[0],
        layout.voice[1] + panelFloat,
        layout.voice[2]
      );
      voicePanel.current.visible = pPanels > 0.01;
    }
    if (pulsePanel.current) {
      pulsePanel.current.scale.setScalar(
        Math.max(0.001, layout.panelScale * (EASE.outCubic(seg(10.5, 12.1)) || 0))
      );
      pulsePanel.current.position.set(
        layout.pulse[0],
        layout.pulse[1] + Math.sin(t * 0.8 + 1.7) * 0.05,
        layout.pulse[2]
      );
      pulsePanel.current.visible = pPanels > 0.01;
    }
  });

  return (
    <>
      {/* ---------- cinematic lighting ---------- */}
      <ambientLight intensity={0.52} color="#e3d2e6" />
      <directionalLight position={[2.8, 5.5, 4]} intensity={1.15} color="#ffe9f3" />
      <pointLight position={[-3.4, 2.6, 2.4]} intensity={1.5} color={HOT} distance={10} />
      <pointLight position={[4.2, 1.4, 2.4]} intensity={1.1} color={VIOLET} distance={9} />
      <pointLight position={[1.2, 3, 5]} intensity={0.85} color={PEARL} distance={8} />

      {/* ---------- dedicated face lighting for the ASHA worker ----------
       *
       * The previous single point light was 0.75 intensity at 3 units with
       * inverse-square falloff, so it delivered almost nothing to her face.
       * These three lights are short-range and warm, placed in front of and
       * slightly above her, so her face becomes the brightest, most readable
       * surface in the scene while the purple environment stays moody.
       * They are parented to the worker group, so they follow her exactly.
       */}
      <group position={[WORKER_X, 0, 0]}>
        {/* Key: soft warm frontal light with a high penumbra -> real,
            gentle shadows on the nose and cheekbones.
            `volumetric={false}` — drei's SpotLight renders a visible cone
            mesh by default, which would wash out the face. */}
        <SpotLight
          position={[0.28, 2.62, 1.45]}
          target={faceTarget}
          color="#ffe2c8"
          intensity={20}
          angle={0.36}
          penumbra={0.92}
          attenuation={2.0}
          anglePower={2}
          distance={5.5}
          volumetric={false}
          castShadow={false}
        />
        {/* Fill: lifts the shadow side so no feature is lost in darkness. */}
        <pointLight
          position={[-0.35, 1.98, 0.95]}
          intensity={1.2}
          color="#ffd6b8"
          distance={3.2}
          decay={1.25}
        />
        {/* Gentle bounce from below, like light reflecting off the floor. */}
        <pointLight
          position={[0.1, 1.42, 0.72]}
          intensity={0.55}
          color="#ffe5d4"
          distance={2.5}
          decay={1.25}
        />
        {/* Pink rim from behind-right separates her from the dark background. */}
        <pointLight
          position={[-0.55, 2.25, -0.75]}
          intensity={1.05}
          color={HOT}
          distance={2.6}
          decay={1.5}
        />
      </group>

      {/* volumetric light shafts (target must be part of the scene graph) */}
      <primitive object={lightTarget} />
      <primitive object={faceTarget} />
      <SpotLight
        position={[-3.4, 5.8, 2.4]}
        target={lightTarget}
        color={HOT}
        intensity={2.4}
        angle={0.52}
        penumbra={0.7}
        attenuation={5}
        anglePower={4}
        distance={13}
        opacity={0.28}
        volumetric
      />
      <SpotLight
        position={[4.6, 5.4, 2.0]}
        target={lightTarget}
        color={VIOLET}
        intensity={1.8}
        angle={0.5}
        penumbra={0.7}
        attenuation={5}
        anglePower={4}
        distance={12}
        opacity={0.24}
        volumetric
      />

      {/* ---------- environment layers ---------- */}
      <GlowBackdrop />
      <Pillars />
      <ReflectiveFloor />

      <Sparkles count={85} scale={[9, 5, 5]} size={1.7} speed={0.25} color={PINK} opacity={0.42} />
      <Sparkles count={50} scale={[8, 4.5, 5]} size={2.2} speed={0.18} color={LAV} opacity={0.32} />
      {/* foreground dust, closer to camera */}
      <Sparkles count={45} scale={[5, 3, 2]} size={3} speed={0.3} color={PEARL} opacity={0.25} position={[0, 1.8, 3.4]} />

      {/* ================= characters (sways with pointer) ================= */}
      <group ref={group} position={[WORKER_X, 0, 0]}>
        {/* Particle squares: QR hologram -> scatter -> silhouette -> aura */}
        <instancedMesh ref={squaresRef} args={[undefined, undefined, scene.N]}>
          <boxGeometry args={[1, 1, 0.35]} />
          <meshBasicMaterial toneMapped={false} />
        </instancedMesh>

        {/* The materialized ASHA worker - large, right of centre */}
        <group ref={workerGroup} visible={false}>
          <AshaWorker />
        </group>

        {/* animated floor rings around her */}
        <FloorRings />

        {/* holographic welcome rings during materialization */}
        <mesh ref={holoRing} position={[0, 1.4, 0]} rotation={[Math.PI / 2, 0, 0]} visible={false}>
          <torusGeometry args={[1.05, 0.012, 12, 64]} />
          <meshBasicMaterial color={HOT} transparent opacity={0.5} toneMapped={false} />
        </mesh>
        <mesh ref={holoRing2} position={[0, 1.4, 0]} rotation={[Math.PI / 2, 0.4, 0]} visible={false}>
          <torusGeometry args={[1.35, 0.008, 12, 64]} />
          <meshBasicMaterial color={LAV} transparent opacity={0.4} toneMapped={false} />
        </mesh>

        {/* Tara floats in beside her, above shoulder level */}
        <group ref={taraGroup} visible={false}>
          <Tara state={taraState} scale={0.58} position={[0, 0, 0.35]} />
        </group>
      </group>

      {/* ================= holographic panels (independent float) ================= */}
      <group ref={voicePanel} visible={false}>
        <VoicePanel rotation={[0, layout.voiceRot, 0]} scale={1} />
      </group>
      <group ref={pulsePanel} visible={false}>
        <PulseThreadPanel rotation={[0, layout.pulseRot, 0]} scale={1} />
      </group>

      {/* glowing connections from the worker to each panel */}
      <group>
        <ConnectionBeam
          from={[WORKER_X - 0.3, 2.1, 0]}
          to={[layout.voice[0] + 0.75, layout.voice[1] - 0.45, layout.voice[2]]}
          color={PINK}
          opacity={0.55}
          activeRef={tRef}
        />
        <ConnectionBeam
          from={[WORKER_X + 0.5, 1.9, 0.1]}
          to={[layout.pulse[0] - 0.6, layout.pulse[1] - 0.55, layout.pulse[2]]}
          color={LAV}
          opacity={0.55}
          activeRef={tRef}
        />
      </group>

      <ContactShadows
        position={[0, 0.015, 0]}
        opacity={0.4}
        scale={7}
        blur={2.8}
        far={2.6}
        color="#050308"
      />
    </>
  );
}

/* soft reflective floor (kept as its own tiny component for readability) */
function ReflectiveFloor() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
      <circleGeometry args={[17, 48]} />
      <MeshReflectorMaterial
        resolution={768}
        mirror={0.42}
        blur={[320, 90]}
        mixBlur={14}
        mixStrength={1.5}
        depthScale={0.7}
        color="#150d1c"
        metalness={0.55}
        roughness={0.82}
      />
    </mesh>
  );
}
