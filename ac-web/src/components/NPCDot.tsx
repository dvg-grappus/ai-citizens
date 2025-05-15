import React, { useEffect, useRef, useState } from 'react';
import { Circle, Text as KonvaText, Group } from 'react-konva';
import Konva from 'konva'; // Import Konva for Tween
import type { DisplayNPC } from '../store/simStore'; // Assuming DisplayNPC includes x, y, emoji, name, id
import { useSimActions } from '../store/simStore'; // Import actions hook

interface NPCDotProps {
    npc: DisplayNPC;
    color: string; // Pass color as a prop
}

const NPCDotSize = 12; // Was 8, increased to 12 (1.5x, can go more if needed)
const EmojiSize = 20;  // Was 14, increased to 20
const NameFontSize = 10; // Was 8, increased to 10
const ANIMATION_DURATION_SECONDS = 1.5; // Slightly reduced for responsiveness
const IDLE_MOVEMENT_RANGE = 5; // Maximum pixel range for random idle movements
const IDLE_MOVEMENT_INTERVAL_MS = 2000; // Time between idle animations

const NPCDot: React.FC<NPCDotProps> = ({ npc, color }) => {
    const groupRef = useRef<Konva.Group>(null); // Ref for the Konva Group
    const { openNPCDetailModal } = useSimActions(); // Get the action
    const apiUrl = import.meta.env.VITE_API_URL; // Needed for the action
    const lastPositionRef = useRef({ x: npc.x || 0, y: npc.y || 0 });
    const idleAnimationTimerRef = useRef<number | null>(null);
    const isMovingRef = useRef(false);

    // Use state for the initial position to ensure the Group doesn't get x/y props updated directly by React render cycle
    const [currentX, setCurrentX] = useState(npc.x || 0);
    const [currentY, setCurrentY] = useState(npc.y || 0);

    // Effect to handle setting initial position or hard jumps if npc.id changes
    useEffect(() => {
        if (groupRef.current) {
            groupRef.current.x(npc.x || 0);
            groupRef.current.y(npc.y || 0);
            setCurrentX(npc.x || 0); // Update state for initial render if needed
            setCurrentY(npc.y || 0);
            lastPositionRef.current = { x: npc.x || 0, y: npc.y || 0 };
        }
    }, [npc.id]);

    // Effect to animate to new target npc.x, npc.y from props
    useEffect(() => {
        if (groupRef.current && typeof npc.x === 'number' && typeof npc.y === 'number') {
            // Check if position has actually changed
            if (npc.x !== lastPositionRef.current.x || npc.y !== lastPositionRef.current.y) {
                isMovingRef.current = true;
                
                // Clear any existing idle animation timer
                if (idleAnimationTimerRef.current !== null) {
                    window.clearTimeout(idleAnimationTimerRef.current);
                    idleAnimationTimerRef.current = null;
                }
                
                // Animate from current *visual* position to new target npc.x, npc.y
                const tween = new Konva.Tween({
                    node: groupRef.current,
                    duration: ANIMATION_DURATION_SECONDS,
                    x: npc.x,
                    y: npc.y,
                    easing: Konva.Easings.EaseInOut,
                    onFinish: () => {
                        // Ensure final position is accurately set if tween is interrupted or imprecise
                        if (groupRef.current) {
                            groupRef.current.x(npc.x);
                            groupRef.current.y(npc.y);
                            lastPositionRef.current = { x: npc.x, y: npc.y };
                            isMovingRef.current = false;
                            
                            // Start idle animations after completing a move
                            startIdleAnimations();
                        }
                    }
                });
                tween.play();
                return () => {
                    tween.destroy();
                };
            }
        }
    }, [npc.x, npc.y]); // Trigger ONLY when target coordinates change

    // Effect to handle idle animations when NPC isn't moving
    useEffect(() => {
        // Start idle animations on mount
        startIdleAnimations();
        
        return () => {
            // Clean up on unmount
            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
            }
        };
    }, []);

    const startIdleAnimations = () => {
        // Clear any existing timer
        if (idleAnimationTimerRef.current !== null) {
            window.clearTimeout(idleAnimationTimerRef.current);
        }
        
        // Schedule the next idle animation
        idleAnimationTimerRef.current = window.setTimeout(() => {
            if (!isMovingRef.current && groupRef.current) {
                // Generate random micro-movement within IDLE_MOVEMENT_RANGE
                const offsetX = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
                const offsetY = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
                
                // Get the base position stored in lastPositionRef
                const baseX = lastPositionRef.current.x;
                const baseY = lastPositionRef.current.y;
                
                // Animate to the slightly offset position
                const tween = new Konva.Tween({
                    node: groupRef.current,
                    duration: 0.8, // Quick, subtle movement
                    x: baseX + offsetX,
                    y: baseY + offsetY,
                    easing: Konva.Easings.EaseInOut,
                    onFinish: () => {
                        // After moving to offset position, schedule return to base position
                        if (groupRef.current) {
                            setTimeout(() => {
                                if (groupRef.current) {
                                    // Return to base position
                                    const returnTween = new Konva.Tween({
                                        node: groupRef.current,
                                        duration: 0.8,
                                        x: baseX,
                                        y: baseY,
                                        easing: Konva.Easings.EaseInOut,
                                        onFinish: startIdleAnimations // Continue the cycle
                                    });
                                    returnTween.play();
                                }
                            }, 500); // Small pause at the offset position
                        }
                    }
                });
                tween.play();
            } else {
                // If we're already moving due to an actual position change, just reschedule
                startIdleAnimations();
            }
        }, IDLE_MOVEMENT_INTERVAL_MS + Math.random() * 1000); // Add some randomness to the interval
    };

    const handleDotClick = () => {
        console.log(`NPCDot clicked: ${npc.name} (ID: ${npc.id})`);
        if (apiUrl) {
            openNPCDetailModal(npc.id, apiUrl);
        } else {
            console.error("Cannot open NPC details: API URL is not defined.");
            // Optionally push a log to the store: actions.pushLog("Error: Missing API URL for details.");
        }
    };

    // Render only if initial npc.x and npc.y are valid numbers
    if (typeof npc.x !== 'number' || typeof npc.y !== 'number') {
        return null; 
    }

    return (
        // Group x/y props are now for initial placement only, controlled by useState if necessary,
        // but more robustly, the first useEffect sets the node position.
        // For tweening to work best, group x/y props should not change once tweening starts for that target.
        // We set initial position via ref, and let tween control it.
        <Group 
            ref={groupRef} 
            key={npc.id} 
            id={npc.id} 
            x={currentX} // Use state for initial/non-tweened position
            y={currentY} // Use state for initial/non-tweened position
            onClick={handleDotClick} 
            onTap={handleDotClick} 
            hitGraphEnabled={true}
        >
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
