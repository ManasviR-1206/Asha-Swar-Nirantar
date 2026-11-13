import { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import * as THREE from "three";

/**
 * TARA — the AI companion robot.
 * Pearl-white glossy body, dark glass visor, expressive glowing eyes,
 * antenna light, floating arms, glowing heart emblem.
 *
 * Props:
 *  - state: "idle" | "wave" | "listen" | "think" | "cover" | "happy"
 *  - gaze: {x, y} in [-1, 1] to make eyes/head follow a point (defaults to pointer)
 *  - scale, position
 */
export default function Tara({
  state = "idle",
  gaze = null,
  scale = 1,
  position = [0, 0, 0],
}) {
  const root = useRef();
  const body = useRef();
  const head = useRef();
  const eyeGroup = useRef();
  const eyeL = useRef();
  const eyeR = useRef();
  const armL = useRef();
  const armR = useRef();
  const antenna = useRef();
  const heart = useRef();

  // Blink state stored on refs (no re-renders)
  const blink = useRef({ next: 2.2, closing: 0 });

  // Arm pose targets per state
  const poses = useMemo(
    () => ({
      idle: {
        armL: { pos: [-0.62, -0.05, 0], rot: [0, 0, 0.25] },
        armR: { pos: [0.62, -0.05, 0], rot: [0, 0, -0.25] },
        headTilt: 0,
        eyesClosed: false,
      },
      wave: {
        armL: { pos: [-0.62, -0.05, 0], rot: [0, 0, 0.25] },
        armR: { pos: [0.72, 0.55, 0.12], rot: [0, 0, -2.0] },
        headTilt: 0.06,
        eyesClosed: false,
      },
      listen: {
        armL: { pos: [-0.58, 0.02, 0.18], rot: [0.35, 0, 0.2] },
        armR: { pos: [0.58, 0.02, 0.18], rot: [0.35, 0, -0.2] },
        headTilt: -0.05,
        eyesClosed: false,
      },
      think: {
        armL: { pos: [-0.62, -0.05, 0], rot: [0, 0, 0.25] },
        armR: { pos: [0.3, 0.5, 0.3], rot: [0.4, 0, -1.2] },
        headTilt: 0.12,
        eyesClosed: false,
      },
      cover: {
        armL: { pos: [-0.2, 0.86, 0.52], rot: [0.15, 0, 1.35] },
        armR: { pos: [0.2, 0.86, 0.52], rot: [0.15, 0, -1.35] },
        headTilt: 0,
        eyesClosed: true,
      },
      happy: {
        armL: { pos: [-0.66, 0.18, 0.05], rot: [0, 0, 0.7] },
        armR: { pos: [0.66, 0.18, 0.05], rot: [0, 0, -0.7] },
        headTilt: -0.08,
        eyesClosed: false,
      },
    }),
    []
  );

  useFrame((r3fState, rawDelta) => {
    const t = r3fState.clock.elapsedTime;
    const clockDelta = Math.min(rawDelta, 0.05);
    const pose = poses[state] || poses.idle;

    // ---- Gentle floating ----
    if (root.current) {
      root.current.position.y = position[1] + Math.sin(t * 1.4) * 0.06;
      root.current.rotation.z = Math.sin(t * 0.7) * 0.015;
    }

    // ---- Head & eyes follow gaze / pointer ----
    let gx = r3fState.pointer.x;
    let gy = r3fState.pointer.y;
    if (gaze) {
      gx = gaze.x;
      gy = gaze.y;
    }
    if (head.current) {
      head.current.rotation.y = THREE.MathUtils.lerp(
        head.current.rotation.y,
        gx * 0.5,
        0.08
      );
      head.current.rotation.x = THREE.MathUtils.lerp(
        head.current.rotation.x,
        pose.headTilt - gy * 0.25,
        0.08
      );
    }
    if (eyeGroup.current) {
      eyeGroup.current.position.x = THREE.MathUtils.lerp(
        eyeGroup.current.position.x,
        gx * 0.06,
        0.1
      );
      eyeGroup.current.position.y = THREE.MathUtils.lerp(
        eyeGroup.current.position.y,
        gy * 0.04,
        0.1
      );
    }

    // ---- Blinking (natural rhythm) ----
    const b = blink.current;
    if (!pose.eyesClosed) {
      if (b.closing > 0) {
        // 0.14s blink: close then reopen
        b.closing -= clockDelta;
        const phase = 1 - Math.abs(b.closing - 0.07) / 0.07;
        const s = Math.max(0.06, 1 - phase);
        eyeL.current && (eyeL.current.scale.y = s);
        eyeR.current && (eyeR.current.scale.y = s);
      } else {
        b.next -= clockDelta;
        if (b.next <= 0) {
          b.closing = 0.14;
          b.next = 2.2 + Math.random() * 2.4;
        }
        eyeL.current && (eyeL.current.scale.y = 1);
        eyeR.current && (eyeR.current.scale.y = 1);
      }
    } else {
      eyeL.current && (eyeL.current.scale.y = 0.02);
      eyeR.current && (eyeR.current.scale.y = 0.02);
    }

    // ---- Arms lerp toward pose ----
    for (const [ref, target] of [
      [armL, pose.armL],
      [armR, pose.armR],
    ]) {
      if (ref.current) {
        ref.current.position.lerp(
          new THREE.Vector3(...target.pos),
          0.12
        );
        ref.current.rotation.x = THREE.MathUtils.lerp(
          ref.current.rotation.x,
          target.rot[0],
          0.12
        );
        ref.current.rotation.z = THREE.MathUtils.lerp(
          ref.current.rotation.z,
          target.rot[2],
          0.12
        );
      }
    }

    // ---- Wave oscillation ----
    if (state === "wave" && armR.current) {
      armR.current.rotation.y = Math.sin(t * 6) * 0.35;
    }

    // ---- Antenna pulse ----
    if (antenna.current) {
      const intensity =
        state === "listen"
          ? 1.6 + Math.sin(t * 8) * 0.8
          : 1 + Math.sin(t * 2.5) * 0.25;
      antenna.current.material.emissiveIntensity = intensity;
    }

    // ---- Heart glow ----
    if (heart.current) {
      const s = 1 + Math.sin(t * 3) * 0.08;
      heart.current.scale.setScalar(s);
    }

    // ---- Happy bounce ----
    if (state === "happy" && root.current) {
      root.current.position.y += Math.abs(Math.sin(t * 5)) * 0.05;
    }
  });

  const pearl = {
    color: "#f2f5f7",
    roughness: 0.18,
    metalness: 0.05,
    clearcoat: 1,
    clearcoatRoughness: 0.15,
  };

  return (
    <group ref={root} position={position} scale={scale}>
      {/* ---- Body ---- */}
      <group ref={body}>
        <RoundedBox args={[0.9, 1.15, 0.75]} radius={0.34} smoothness={8} position={[0, -0.1, 0]}>
          <meshPhysicalMaterial {...pearl} />
        </RoundedBox>

        {/* Chest heart emblem — glowing healthcare heart */}
        <mesh ref={heart} position={[0, 0.08, 0.39]}>
          <sphereGeometry args={[0.075, 24, 24]} />
          <meshStandardMaterial
            color="#ff8ab8"
            emissive="#e84d9b"
            emissiveIntensity={1.5}
            roughness={0.3}
          />
        </mesh>

        {/* Rose-gold collar ring */}
        <mesh position={[0, 0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.46, 0.014, 10, 48]} />
          <meshStandardMaterial color="#b76e79" metalness={0.8} roughness={0.25} />
        </mesh>

        {/* ---- Head ---- */}
        <group ref={head} position={[0, 0.86, 0]}>
          <RoundedBox args={[1.0, 0.78, 0.82]} radius={0.3} smoothness={8}>
            <meshPhysicalMaterial {...pearl} />
          </RoundedBox>

          {/* Dark glass visor */}
          <RoundedBox args={[0.86, 0.56, 0.5]} radius={0.22} smoothness={8} position={[0, 0.02, 0.22]}>
            <meshPhysicalMaterial
              color="#0d1b2a"
              roughness={0.08}
              metalness={0.1}
              clearcoat={1}
              clearcoatRoughness={0.05}
            />
          </RoundedBox>

          {/* Eyes */}
          <group ref={eyeGroup} position={[0, 0.02, 0.48]}>
            <mesh ref={eyeL} position={[-0.17, 0, 0]}>
              <capsuleGeometry args={[0.045, 0.1, 6, 12]} />
              <meshStandardMaterial
                color="#ffc4dd"
                emissive="#f078ad"
                emissiveIntensity={2.4}
              />
            </mesh>
            <mesh ref={eyeR} position={[0.17, 0, 0]}>
              <capsuleGeometry args={[0.045, 0.1, 6, 12]} />
              <meshStandardMaterial
                color="#d8ccff"
                emissive="#bba6ff"
                emissiveIntensity={2.4}
              />
            </mesh>
          </group>

          {/* Blush pads */}
          <mesh position={[-0.33, -0.12, 0.4]} rotation={[0, 0, 0]}>
            <sphereGeometry args={[0.05, 16, 16]} />
            <meshStandardMaterial color="#ffd9cf" roughness={0.9} transparent opacity={0.85} />
          </mesh>
          <mesh position={[0.33, -0.12, 0.4]}>
            <sphereGeometry args={[0.05, 16, 16]} />
            <meshStandardMaterial color="#ffd9cf" roughness={0.9} transparent opacity={0.85} />
          </mesh>

          {/* Antenna */}
          <group position={[0, 0.42, 0]}>
            <mesh position={[0, 0.08, 0]}>
              <cylinderGeometry args={[0.015, 0.02, 0.18, 8]} />
              <meshStandardMaterial color="#dfe6ea" metalness={0.4} roughness={0.3} />
            </mesh>
            <mesh ref={antenna} position={[0, 0.2, 0]}>
              <sphereGeometry args={[0.05, 16, 16]} />
              <meshStandardMaterial
                color="#ffc4dd"
                emissive="#e84d9b"
                emissiveIntensity={1.5}
              />
            </mesh>
          </group>
        </group>

        {/* ---- Arms (floating capsules) ---- */}
        <group ref={armL} position={[-0.62, -0.05, 0]}>
          <mesh rotation={[0, 0, 0.2]}>
            <capsuleGeometry args={[0.09, 0.34, 8, 16]} />
            <meshPhysicalMaterial {...pearl} />
          </mesh>
          <mesh position={[0, -0.28, 0]}>
            <sphereGeometry args={[0.11, 16, 16]} />
            <meshPhysicalMaterial color="#e6ebee" roughness={0.25} clearcoat={0.8} />
          </mesh>
        </group>
        <group ref={armR} position={[0.62, -0.05, 0]}>
          <mesh rotation={[0, 0, -0.2]}>
            <capsuleGeometry args={[0.09, 0.34, 8, 16]} />
            <meshPhysicalMaterial {...pearl} />
          </mesh>
          <mesh position={[0, -0.28, 0]}>
            <sphereGeometry args={[0.11, 16, 16]} />
            <meshPhysicalMaterial color="#e6ebee" roughness={0.25} clearcoat={0.8} />
          </mesh>
        </group>
      </group>
    </group>
  );
}
