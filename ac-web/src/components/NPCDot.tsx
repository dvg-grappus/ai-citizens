import React, { useEffect, useRef, useState } from 'react';
import { Circle, Text as KonvaText, Group } from 'react-konva';
import Konva from 'konva'; // Import Konva for Tween
import type { DisplayNPC } from '../store/simStore'; // Assuming DisplayNPC includes x, y, emoji, name, id

interface NPCDotProps {
    npc: DisplayNPC;
    color: string; // Pass color as a prop
}

const NPCDotSize = 12; // Was 8, increased to 12 (1.5x, can go more if needed)
const EmojiSize = 20;  // Was 14, increased to 20
const NameFontSize = 10; // Was 8, increased to 10
const ANIMATION_DURATION_SECONDS = 2.0; // Slower animation

const NPCDot: React.FC<NPCDotProps> = ({ npc, color }) => {
    const groupRef = useRef<Konva.Group>(null); // Ref for the Konva Group
    // Store initial position to avoid re-setting it if props don't actually change target
    const [initialX, setInitialX] = useState(npc.x);
    const [initialY, setInitialY] = useState(npc.y);

    useEffect(() => {
        // Set initial position of the Konva Group node if it hasn't been set
        // or if the npc prop identity changes (which means it's a new NPC dot being rendered)
        if (groupRef.current) {
            if (groupRef.current.x() !== npc.x || groupRef.current.attrs.id !== npc.id) { // Simple check if it is a new npc or first render
                groupRef.current.x(npc.x || 0); // Set initial position directly
                setInitialX(npc.x || 0);
            }
            if (groupRef.current.y() !== npc.y || groupRef.current.attrs.id !== npc.id) {
                groupRef.current.y(npc.y || 0);
                setInitialY(npc.y || 0);
            }
        }
    }, [npc.id]); // Depend on npc.id to reset initial position for new/recycled dot components

    useEffect(() => {
        if (groupRef.current && typeof npc.x === 'number' && typeof npc.y === 'number') {
            // Only tween if the target position is different from the current animated position
            if (groupRef.current.x() !== npc.x || groupRef.current.y() !== npc.y) {
                const tween = new Konva.Tween({
                    node: groupRef.current,
                    duration: ANIMATION_DURATION_SECONDS,
                    x: npc.x,
                    y: npc.y,
                    easing: Konva.Easings.EaseInOut,
                });
                tween.play();
                return () => tween.destroy();
            }
        }
    }, [npc.x, npc.y]); // Trigger animation when target npc.x or npc.y from store changes

    // Initial position is set directly, subsequent updates are animated by the tween.
    // If npc.x/y is initially undefined, it might cause issues; ensure valid initial coords.
    // The check below handles rendering only if initial coords are valid.
    if (typeof initialX !== 'number' || typeof initialY !== 'number') {
        // This might hide the dot initially if x/y are not set in the store yet.
        // Consider setting initial groupRef.current position if needed and x/y are valid.
        return null; 
    }

    return (
        // Initial position is set by the first useEffect or the initialX/initialY state.
        // The Group x/y props are now only for initial rendering.
        <Group ref={groupRef} key={npc.id} id={npc.id} x={initialX} y={initialY}>
            <Circle radius={NPCDotSize} fill={color} stroke="#fff" strokeWidth={0.5} shadowBlur={6} shadowColor="black" shadowOpacity={0.7} />
            {npc.emoji && (
                <KonvaText
                    text={npc.emoji}
                    fontSize={EmojiSize}
                    x={-EmojiSize / 2} // Adjusted for better centering
                    y={-EmojiSize - NPCDotSize - 2} // Position further above dot
                    fill="#fff"
                    shadowColor="black"
                    shadowBlur={2}
                    shadowOffsetX={1}
                    shadowOffsetY={1}
                    listening={false} // Emojis and text usually don't need to be interactive
                />
            )}
            {npc.name && (
                 <KonvaText
                    text={npc.name}
                    fontSize={NameFontSize}
                    fill="#e0e0e0"
                    y={NPCDotSize + 4} // Position further below dot
                    offsetX={(npc.name.length * NameFontSize * 0.6) / 2} // Adjusted centering
                    shadowColor="black"
                    shadowBlur={1}
                    listening={false}
                />
            )}
        </Group>
    );
};

export default NPCDot;
