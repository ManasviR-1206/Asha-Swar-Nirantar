import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import * as THREE from "three";

/**
 * Stylised female Indian ASHA worker — built entirely from 3D primitives.
 * Wears a teal-green saree with mint/gold border, an ASHA identity card,
 * and holds a tablet. Warm, friendly, professional.
 *
 * The hero scene animates her entrance (scale/rise) externally.
 * Internal: gentle breathing, blinking, subtle head sway.
 */
export default function AshaWorker({ position = [0, 0, 0], scale = 1 }) {
  const root = useRef();
  const head = useRef();
  const eyeL = useRef();
  const eyeR = useRef();
  const armR = useRef();
  const blink = useRef({ next: 3, closing: 0 });

  const SKIN = "#bf7d54";
  const SAREE = "#b0557f"; // dusty-rose saree
  const SAREE_DEEP = "#8d3d63";
  const HAIR = "#191009";
  const ROSEGOLD = "#c98a8e";
  const GOLD = "#d9a08b";

  /* Skin shading.
   *
   * The colour stays the natural warm radiant Indian skin tone. The face gets a
   * warm subsurface emissive so the features remain bright, vibrant, and legible
   * against the dark purple-pink hero scene without washing out into flat white.
   * Roughness is tuned to 0.52 for a soft, velvety natural skin sheen.
   */
  const SKIN_ROUGHNESS = 0.52;
  const FACE_EMISSIVE = "#5c321d";
  const BODY_EMISSIVE = "#361b11";

  const skinMaterial = (emissive, emissiveIntensity) => (
    <meshStandardMaterial
      color={SKIN}
      roughness={SKIN_ROUGHNESS}
      emissive={emissive}
      emissiveIntensity={emissiveIntensity}
    />
  );

  useFrame((r3fState, rawDelta) => {
    const t = r3fState.clock.elapsedTime;
    const dt = Math.min(rawDelta, 0.05);

    // Gentle breathing + sway
    if (root.current) {
      root.current.rotation.y = Math.sin(t * 0.5) * 0.08;
    }
    if (head.current) {
      head.current.rotation.z = Math.sin(t * 0.6) * 0.03;
      head.current.rotation.x = Math.sin(t * 0.45) * 0.03;
    }

    // Blink
    const b = blink.current;
    if (b.closing > 0) {
      b.closing -= dt;
      const phase = 1 - Math.abs(b.closing - 0.07) / 0.07;
      const s = Math.max(0.08, 1 - phase);
      eyeL.current && (eyeL.current.scale.y = s);
      eyeR.current && (eyeR.current.scale.y = s);
    } else {
      b.next -= dt;
      if (b.next <= 0) {
        b.closing = 0.14;
        b.next = 2.5 + Math.random() * 3;
      }
      eyeL.current && (eyeL.current.scale.y = 1);
      eyeR.current && (eyeR.current.scale.y = 1);
    }

    // Right arm: gentle welcoming sway
    if (armR.current) {
      armR.current.rotation.z = -0.28 + Math.sin(t * 0.9) * 0.04;
    }
  });

  return (
    <group ref={root} position={position} scale={scale}>
      {/* ================= HEAD ================= */}
      <group ref={head} position={[0, 1.56, 0]}>
        {/* Face - bright, naturally illuminated Indian skin */}
        <mesh scale={[0.95, 1.05, 0.92]}>
          <sphereGeometry args={[0.16, 32, 32]} />
          {skinMaterial(FACE_EMISSIVE, 0.60)}
        </mesh>

        {/* Soft cheek warmth contours */}
        <mesh position={[-0.082, -0.015, 0.125]}>
          <sphereGeometry args={[0.024, 12, 12]} />
          <meshStandardMaterial color="#c97b63" roughness={0.65} emissive="#663220" emissiveIntensity={0.35} />
        </mesh>
        <mesh position={[0.082, -0.015, 0.125]}>
          <sphereGeometry args={[0.024, 12, 12]} />
          <meshStandardMaterial color="#c97b63" roughness={0.65} emissive="#663220" emissiveIntensity={0.35} />
        </mesh>

        {/* Nose */}
        <mesh position={[0, -0.015, 0.15]}>
          <sphereGeometry args={[0.017, 12, 12]} />
          {skinMaterial(FACE_EMISSIVE, 0.65)}
        </mesh>

        {/* Smile — torus arc curving downward = warm smile */}
        <mesh position={[0, -0.065, 0.135]} rotation={[0, 0, Math.PI]}>
          <torusGeometry args={[0.035, 0.006, 8, 20, Math.PI]} />
          <meshStandardMaterial color="#8a3838" roughness={0.4} />
        </mesh>

        {/* Eyes */}
        <mesh ref={eyeL} position={[-0.058, 0.02, 0.14]}>
          <sphereGeometry args={[0.0145, 12, 12]} />
          <meshStandardMaterial color="#1d150f" roughness={0.28} />
        </mesh>
        <mesh ref={eyeR} position={[0.058, 0.02, 0.14]}>
          <sphereGeometry args={[0.0145, 12, 12]} />
          <meshStandardMaterial color="#1d150f" roughness={0.28} />
        </mesh>
        {/* Eye glints — slightly larger so the eyes stay readable */}
        <mesh position={[-0.0525, 0.0265, 0.1525]}>
          <sphereGeometry args={[0.0052, 8, 8]} />
          <meshBasicMaterial color="#ffffff" toneMapped={false} />
        </mesh>
        <mesh position={[0.0635, 0.0265, 0.1525]}>
          <sphereGeometry args={[0.0052, 8, 8]} />
          <meshBasicMaterial color="#ffffff" toneMapped={false} />
        </mesh>
        {/* Lower catch-light in the iris keeps the eye from looking hollow */}
        <mesh position={[-0.056, 0.0125, 0.1525]}>
          <sphereGeometry args={[0.0026, 6, 6]} />
          <meshBasicMaterial color="#bba6ff" toneMapped={false} />
        </mesh>
        <mesh position={[0.06, 0.0125, 0.1525]}>
          <sphereGeometry args={[0.0026, 6, 6]} />
          <meshBasicMaterial color="#bba6ff" toneMapped={false} />
        </mesh>

        {/* Eyebrows */}
        <mesh position={[-0.058, 0.062, 0.135]} rotation={[0, 0, -0.12]}>
          <boxGeometry args={[0.045, 0.006, 0.01]} />
          <meshStandardMaterial color={HAIR} roughness={0.8} />
        </mesh>
        <mesh position={[0.058, 0.062, 0.135]} rotation={[0, 0, 0.12]}>
          <boxGeometry args={[0.045, 0.006, 0.01]} />
          <meshStandardMaterial color={HAIR} roughness={0.8} />
        </mesh>

        {/* Bindi */}
        <mesh position={[0, 0.075, 0.148]}>
          <sphereGeometry args={[0.008, 10, 10]} />
          <meshStandardMaterial color="#c0392b" roughness={0.4} />
        </mesh>

        {/* Hair — cap + bun */}
        <mesh position={[0, 0.045, -0.03]} scale={[1.02, 1.02, 1.02]}>
          <sphereGeometry args={[0.165, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.62]} />
          <meshStandardMaterial color={HAIR} roughness={0.55} />
        </mesh>
        {/* Hair back volume */}
        <mesh position={[0, 0.02, -0.075]} scale={[0.98, 0.95, 0.7]}>
          <sphereGeometry args={[0.16, 24, 24]} />
          <meshStandardMaterial color={HAIR} roughness={0.55} />
        </mesh>
        {/* Bun with small mint flower */}
        <mesh position={[0, 0.12, -0.16]}>
          <sphereGeometry args={[0.075, 20, 20]} />
          <meshStandardMaterial color={HAIR} roughness={0.55} />
        </mesh>
        <mesh position={[0.045, 0.15, -0.15]}>
          <sphereGeometry args={[0.02, 10, 10]} />
          <meshStandardMaterial color="#f078ad" roughness={0.4} />
        </mesh>

        {/* Earrings */}
        <mesh position={[-0.155, -0.03, 0.02]}>
          <sphereGeometry args={[0.012, 10, 10]} />
          <meshStandardMaterial color={GOLD} metalness={0.7} roughness={0.3} />
        </mesh>
        <mesh position={[0.155, -0.03, 0.02]}>
          <sphereGeometry args={[0.012, 10, 10]} />
          <meshStandardMaterial color={GOLD} metalness={0.7} roughness={0.3} />
        </mesh>
      </group>

      {/* ================= NECK + JEWELLERY ================= */}
      <mesh position={[0, 1.4, 0]}>
        <cylinderGeometry args={[0.05, 0.06, 0.12, 12]} />
        {skinMaterial(BODY_EMISSIVE, 0.3)}
      </mesh>
      {/* Rose-gold necklace */}
      <mesh position={[0, 1.31, 0.055]} rotation={[Math.PI / 2.35, 0, 0]}>
        <torusGeometry args={[0.062, 0.007, 8, 28]} />
        <meshStandardMaterial color={ROSEGOLD} metalness={0.75} roughness={0.28} />
      </mesh>
      {/* Pendant */}
      <mesh position={[0, 1.25, 0.09]}>
        <sphereGeometry args={[0.014, 10, 10]} />
        <meshStandardMaterial color={ROSEGOLD} metalness={0.75} roughness={0.25} />
      </mesh>

      {/* ================= TORSO (blouse) ================= */}
      <mesh position={[0, 1.18, 0]} scale={[1, 1, 0.8]}>
        <capsuleGeometry args={[0.17, 0.22, 8, 20]} />
        <meshStandardMaterial color={SAREE_DEEP} roughness={0.75} />
      </mesh>

      {/* ================= SAREE SKIRT ================= */}
      <mesh position={[0, 0.56, 0]}>
        <cylinderGeometry args={[0.17, 0.34, 0.98, 24]} />
        <meshStandardMaterial color={SAREE} roughness={0.8} />
      </mesh>
      {/* Pleat fold lines */}
      {[-0.07, 0, 0.07].map((x, i) => (
        <mesh key={i} position={[x * 1.6, 0.56, 0.29]} rotation={[0.04, 0, 0]}>
          <boxGeometry args={[0.006, 0.9, 0.01]} />
          <meshStandardMaterial color={SAREE_DEEP} roughness={0.8} />
        </mesh>
      ))}
      {/* Mint hem border → pink */}
      <mesh position={[0, 0.1, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.335, 0.014, 10, 40]} />
        <meshStandardMaterial color="#f078ad" roughness={0.45} />
      </mesh>
      {/* Gold hem accent */}
      <mesh position={[0, 0.13, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.322, 0.006, 8, 40]} />
        <meshStandardMaterial color={GOLD} metalness={0.6} roughness={0.35} />
      </mesh>

      {/* ================= SAREE PALLU (drape over shoulder) ================= */}
      <mesh position={[0.06, 1.2, 0.1]} rotation={[0.35, -0.25, 0.5]} scale={[1, 1, 0.55]}>
        <capsuleGeometry args={[0.075, 0.42, 8, 16]} />
        <meshStandardMaterial color={SAREE} roughness={0.8} />
      </mesh>
      {/* Pallu gold border line */}
      <mesh position={[-0.03, 1.24, 0.19]} rotation={[0.35, -0.25, 0.5]}>
        <cylinderGeometry args={[0.004, 0.004, 0.5, 6]} />
        <meshStandardMaterial color={GOLD} metalness={0.6} roughness={0.35} />
      </mesh>

      {/* ================= ASHA IDENTITY CARD ================= */}
      {/* Lanyard */}
      <mesh position={[0, 1.28, 0.16]} rotation={[0.25, 0, 0]}>
        <cylinderGeometry args={[0.004, 0.004, 0.16, 6]} />
        <meshStandardMaterial color="#e84d9b" roughness={0.5} />
      </mesh>
      <group position={[0, 1.17, 0.2]} rotation={[0.12, 0, 0.03]}>
        <RoundedBox args={[0.115, 0.15, 0.012]} radius={0.015} smoothness={4}>
          <meshStandardMaterial color="#fff7fc" roughness={0.4} />
        </RoundedBox>
        {/* Card content stripes */}
        <mesh position={[0, 0.038, 0.008]}>
          <boxGeometry args={[0.08, 0.012, 0.002]} />
          <meshStandardMaterial color="#e84d9b" emissive="#e84d9b" emissiveIntensity={0.25} />
        </mesh>
        <mesh position={[0, 0.008, 0.008]}>
          <boxGeometry args={[0.085, 0.008, 0.002]} />
          <meshStandardMaterial color="#28152d" opacity={0.55} transparent />
        </mesh>
        <mesh position={[0, -0.018, 0.008]}>
          <boxGeometry args={[0.085, 0.008, 0.002]} />
          <meshStandardMaterial color="#28152d" opacity={0.55} transparent />
        </mesh>
        {/* ASHA text bar */}
        <mesh position={[0, -0.05, 0.008]}>
          <boxGeometry args={[0.06, 0.016, 0.002]} />
          <meshStandardMaterial color="#bba6ff" opacity={0.9} transparent />
        </mesh>
      </group>

      {/* ================= ARMS ================= */}
      {/* Left arm — bent forward, holding tablet */}
      <group position={[-0.17, 1.22, 0]} rotation={[0.15, 0, 0.3]}>
        <mesh position={[0, -0.14, 0]}>
          <capsuleGeometry args={[0.048, 0.2, 8, 16]} />
          {skinMaterial(BODY_EMISSIVE, 0.3)}
        </mesh>
        <group position={[-0.03, -0.3, 0.06]} rotation={[-0.85, 0, -0.25]}>
          <mesh position={[0, -0.12, 0]}>
            <capsuleGeometry args={[0.042, 0.16, 8, 16]} />
            {skinMaterial(BODY_EMISSIVE, 0.3)}
          </mesh>
          {/* Tablet */}
          <group position={[-0.02, -0.28, 0.08]} rotation={[1.25, 0, 0.15]}>
            <RoundedBox args={[0.24, 0.32, 0.018]} radius={0.02} smoothness={4}>
              <meshStandardMaterial color="#241826" roughness={0.35} />
            </RoundedBox>
            <mesh position={[0, 0, 0.011]}>
              <planeGeometry args={[0.205, 0.285]} />
              <meshStandardMaterial
                color="#2a1330"
                emissive="#e84d9b"
                emissiveIntensity={0.45}
                roughness={0.2}
              />
            </mesh>
            {/* Screen data bars */}
            <mesh position={[-0.03, 0.04, 0.013]}>
              <boxGeometry args={[0.1, 0.012, 0.001]} />
              <meshBasicMaterial color="#f078ad" />
            </mesh>
            <mesh position={[-0.035, 0.005, 0.013]}>
              <boxGeometry args={[0.08, 0.01, 0.001]} />
              <meshBasicMaterial color="#bba6ff" />
            </mesh>
            <mesh position={[-0.025, -0.03, 0.013]}>
              <boxGeometry args={[0.12, 0.008, 0.001]} />
              <meshBasicMaterial color="#f078ad" opacity={0.6} transparent />
            </mesh>
          </group>
        </group>
      </group>

      {/* Right arm — relaxed, gently swaying */}
      <group ref={armR} position={[0.17, 1.22, 0]}>
        <mesh position={[0, -0.15, 0]} rotation={[0, 0, 0]}>
          <capsuleGeometry args={[0.048, 0.22, 8, 16]} />
          {skinMaterial(BODY_EMISSIVE, 0.3)}
        </mesh>
        <mesh position={[0.02, -0.33, 0.02]} rotation={[0, 0, 0.2]}>
          <capsuleGeometry args={[0.042, 0.18, 8, 16]} />
          {skinMaterial(BODY_EMISSIVE, 0.3)}
        </mesh>
        {/* Rose-gold bangles */}
        <mesh position={[0.032, -0.27, 0.024]} rotation={[0, 0, 0.2]}>
          <torusGeometry args={[0.048, 0.005, 8, 24]} />
          <meshStandardMaterial color={ROSEGOLD} metalness={0.75} roughness={0.3} />
        </mesh>
        <mesh position={[0.036, -0.245, 0.026]} rotation={[0, 0, 0.2]}>
          <torusGeometry args={[0.048, 0.004, 8, 24]} />
          <meshStandardMaterial color={ROSEGOLD} metalness={0.75} roughness={0.3} />
        </mesh>
      </group>

      {/* ================= FEET (peeking under saree) ================= */}
      <mesh position={[-0.08, 0.045, 0.08]} scale={[1, 0.6, 1.4]}>
        <sphereGeometry args={[0.05, 12, 12]} />
        <meshStandardMaterial color="#5b4636" roughness={0.7} />
      </mesh>
      <mesh position={[0.08, 0.045, 0.08]} scale={[1, 0.6, 1.4]}>
        <sphereGeometry args={[0.05, 12, 12]} />
        <meshStandardMaterial color="#5b4636" roughness={0.7} />
      </mesh>
    </group>
  );
}
