import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Circle, Text as KonvaText, Group } from 'react-konva';
import Konva from 'konva'; // Import Konva for Tween
import type { DisplayNPC } from '../store/simStore'; // Assuming DisplayNPC includes x, y, emoji, name, id
import { useSimActions, useSimStore } from '../store/simStore'; // Import actions and store

// Define global constants for stage size - we need these for Lounge quadrant detection
const STAGE_WIDTH = 800;  // Must match the size in CanvasStage.tsx
const STAGE_HEIGHT = 600; // Must match the size in CanvasStage.tsx
const AREA_WIDTH = STAGE_WIDTH / 2;
const AREA_HEIGHT = STAGE_HEIGHT / 2;

// Map from area name to position offset
const AREA_OFFSETS: Record<string, {x: number, y: number}> = {
    'Bedroom': { x: 0, y: 0 },
    'Office': { x: AREA_WIDTH, y: 0 },
    'Bathroom': { x: 0, y: AREA_HEIGHT },
    'Lounge': { x: AREA_WIDTH, y: AREA_HEIGHT }
};

interface NPCDotProps {
    npc: DisplayNPC;
    color: string; // Pass color as a prop
}

const NPCDotSize = 12; // Was 8, increased to 12 (1.5x, can go more if needed)
const EmojiSize = 20;  // Was 14, increased to 20
const NameFontSize = 10; // Was 8, increased to 10
const ANIMATION_DURATION_SECONDS = 0.8; // Reduced for more responsive animations

// Very small subtle idle movements to avoid conflicts with backend updates
const IDLE_MOVEMENT_RANGE = 3; // Reduced from 5 to 3
const IDLE_MOVEMENT_INTERVAL_MS = 3000; // Increased to 3 seconds to reduce animation frequency

const NPCDot: React.FC<NPCDotProps> = ({ npc, color }) => {
    // Always initialize these hooks regardless of conditions
    const groupRef = useRef<Konva.Group>(null); // Ref for the Konva Group
    const { openNPCDetailModal } = useSimActions(); // Get the action
    const areas = useSimStore(state => state.areas); // Get areas from store
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'; // Needed for the action
    const lastPositionRef = useRef<{ x: number; y: number } | undefined>(undefined); // Stores last *screen* position
    const idleAnimationTimerRef = useRef<number | null>(null);
    const isMovingRef = useRef(false);
    const currentTweenRef = useRef<Konva.Tween | null>(null);
    const isValidPosition = typeof npc.x === 'number' && typeof npc.y === 'number';

    // Use state for the initial position - hooks must be called in the same order on every render
    const [currentX, setCurrentX] = useState<number>(0); // Initialize to 0 to ensure groupRef is populated
    const [currentY, setCurrentY] = useState<number>(0); // Initialize to 0 to ensure groupRef is populated

    // Function to get the correct screen position based on area
    const getScreenPosition = useCallback(() => {
        const spawn = npc.spawn as {areaId?: string} | undefined;
        const areaId = spawn?.areaId;
        
        if (!areaId || !npc.x || !npc.y) { // Ensure npc.x and npc.y are valid
            // Return a default or last known good if appropriate, or current groupRef position
            if (groupRef.current) return { x: groupRef.current.x(), y: groupRef.current.y() };
            return { x: 0, y: 0 }; // Fallback
        }

        const area = areas.find(a => a.id === areaId);
        if (!area) {
            if (groupRef.current) return { x: groupRef.current.x(), y: groupRef.current.y() };
            return { x: 0, y: 0 }; // Fallback
        }

        const offset = AREA_OFFSETS[area.name] || { x: 0, y: 0 };
        let rawX = offset.x + npc.x;
        let rawY = offset.y + npc.y;
        
        // Apply boundary constraints - keep NPCs within their respective quadrants
        // Add larger margins to ensure name labels are visible
        const MARGIN = 50; // Was 20, changed back to 50 to prevent label cutoff
        
        const minX = offset.x + MARGIN;
        const maxX = offset.x + AREA_WIDTH - MARGIN;
        const minY = offset.y + MARGIN;
        const maxY = offset.y + AREA_HEIGHT - MARGIN;
        
        const constrainedX = Math.max(minX, Math.min(maxX, rawX));
        const constrainedY = Math.max(minY, Math.min(maxY, rawY));
        
        return {
            x: constrainedX,
            y: constrainedY
        };
    }, [npc.x, npc.y, npc.spawn, areas]);

    // Effect for initial placement and when NPC ID changes
    useEffect(() => {
        if (isValidPosition && groupRef.current) {
            console.log(`NPC ${npc.name} (${npc.id}): Initial Placement or ID Change.`);
            const initialScreenPos = getScreenPosition();
            
            groupRef.current.position(initialScreenPos);
            setCurrentX(initialScreenPos.x);
            setCurrentY(initialScreenPos.y);
            lastPositionRef.current = initialScreenPos;
            
            if (currentTweenRef.current) {
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
                idleAnimationTimerRef.current = null;
            }
            isMovingRef.current = false;
            startIdleAnimations(); // Ensure idle animations start after initial placement
        }
    }, [npc.id, isValidPosition]); // REVISED DEPENDENCIES: Removed getScreenPosition and npc.name

    // Effect to animate NPC movement based on prop changes (x, y, or areaId)
    useEffect(() => {
        if (!isValidPosition || !groupRef.current ) return;

        const targetScreenPos = getScreenPosition();

        // If lastPositionRef is not set yet (e.g. initial render flow), let initial placement handle it.
        // This effect should only animate from an established position.
        if (!lastPositionRef.current) {
            // This case should ideally be covered by the initial placement effect.
            // If we reach here, it might mean initial placement didn't set lastPositionRef yet.
            // For safety, one could set it here, but it might cause a jump before animation.
            // console.warn(`NPC ${npc.name} (${npc.id}): Animation effect ran before lastPositionRef was set.`);
            // For now, we assume initial placement effect will set lastPositionRef.current before this runs effectively.
            // Or, we could set the initial position here if lastPositionRef is undefined, then subsequent runs animate.
            // Let's assume the first useEffect handles the very first placement.
            return; 
        }

        const currentVisualPos = lastPositionRef.current; // Animate from the last settled position

        const POSITION_THRESHOLD = 1.0;
        const xDiff = Math.abs(targetScreenPos.x - currentVisualPos.x);
        const yDiff = Math.abs(targetScreenPos.y - currentVisualPos.y);

        if (xDiff > POSITION_THRESHOLD || yDiff > POSITION_THRESHOLD) {
            isMovingRef.current = true;
            // Removed pathPoints update

            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
                idleAnimationTimerRef.current = null;
            }
            if (currentTweenRef.current) {
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
            
            currentTweenRef.current = new Konva.Tween({
                node: groupRef.current, // Konva tweens from current node's x/y
                duration: ANIMATION_DURATION_SECONDS,
                x: targetScreenPos.x,
                y: targetScreenPos.y,
                easing: Konva.Easings.EaseInOut,
                onFinish: () => {
                    if (groupRef.current) {
                        // Position is set by tween. Update ref and state.
                        lastPositionRef.current = { x: groupRef.current.x(), y: groupRef.current.y() };
                        setCurrentX(groupRef.current.x());
                        setCurrentY(groupRef.current.y());
                    }
                    isMovingRef.current = false;
                    startIdleAnimations();
                }
            });
            currentTweenRef.current.play();
        } else {
            // No significant movement, ensure idle animations are running if not already moving
            if (!isMovingRef.current && lastPositionRef.current) { // Added lastPositionRef.current check for safety
                startIdleAnimations();
            }
        }
        // Cleanup function for the tween
        return () => {
            if (currentTweenRef.current) {
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
        };

    }, [npc.x, npc.y, npc.spawn, areas, isValidPosition, getScreenPosition, npc.name]); // npc.name for logs, getScreenPosition due to its own internal deps

    useEffect(() => {
        // This effect ensures idle animations start correctly initially or if props allow
        if (groupRef.current && !isMovingRef.current && isValidPosition && lastPositionRef.current) {
            startIdleAnimations();
        }
        return () => {
            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
                idleAnimationTimerRef.current = null;
            }
            if (currentTweenRef.current) { // Ensure ongoing movement tweens are also cleaned up on unmount
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
        };
    }, [isValidPosition]); // Re-check startIdleAnimations if isValidPosition changes

    const startIdleAnimations = () => {
        if (idleAnimationTimerRef.current !== null) {
            window.clearTimeout(idleAnimationTimerRef.current);
            idleAnimationTimerRef.current = null;
        }
        idleAnimationTimerRef.current = window.setTimeout(() => {
            if (isMovingRef.current || !groupRef.current || !lastPositionRef.current) {
                startIdleAnimations(); 
                return;
            }
            const baseX = lastPositionRef.current.x;
            const baseY = lastPositionRef.current.y;
            const offsetX = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
            const offsetY = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
            
            const tween = new Konva.Tween({
                node: groupRef.current,
                duration: 0.5, 
                x: baseX + offsetX,
                y: baseY + offsetY,
                easing: Konva.Easings.EaseInOut,
                onFinish: () => {
                    if (groupRef.current && !isMovingRef.current) {
                        setTimeout(() => {
                            if (groupRef.current && !isMovingRef.current && lastPositionRef.current) { // check lastPositionRef again
                                const returnTween = new Konva.Tween({
                                    node: groupRef.current,
                                    duration: 0.5,
                                    x: baseX, // Return to the last known major position
                                    y: baseY,
                                    easing: Konva.Easings.EaseInOut,
                                    onFinish: () => {
                                        if (!isMovingRef.current) {
                                            startIdleAnimations();
                                        }
                                    }
                                });
                                currentTweenRef.current = returnTween; // Manage this tween
                                returnTween.play();
                            }
                        }, 800);
                    }
                }
            });
            currentTweenRef.current = tween; // Manage this tween
            tween.play();
        }, IDLE_MOVEMENT_INTERVAL_MS + Math.random() * 1000);
    };

    const handleDotClick = () => {
        if (apiUrl) {
            openNPCDetailModal(npc.id, apiUrl);
        } else {
            console.error("Cannot open NPC details: API URL is not defined.");
        }
    };

    // Render only if position is valid
    if (!isValidPosition) {
        return null; 
    }

    return (
        <Group 
            ref={groupRef} 
            key={npc.id} 
            id={npc.id} 
            x={currentX} 
            y={currentY} 
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
