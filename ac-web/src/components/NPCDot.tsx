import React, { useEffect, useRef, useState } from 'react';
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
    const apiUrl = import.meta.env.VITE_API_URL; // Needed for the action
    const lastPositionRef = useRef({ x: npc.x || 0, y: npc.y || 0 });
    const idleAnimationTimerRef = useRef<number | null>(null);
    const isMovingRef = useRef(false);
    const currentTweenRef = useRef<Konva.Tween | null>(null);
    const isValidPosition = typeof npc.x === 'number' && typeof npc.y === 'number';
    const lastAreaIdRef = useRef<string | undefined>(
        (npc.spawn as { areaId?: string } | undefined)?.areaId
    );

    // Use state for the initial position - hooks must be called in the same order on every render
    const [currentX, setCurrentX] = useState(isValidPosition ? npc.x : 0);
    const [currentY, setCurrentY] = useState(isValidPosition ? npc.y : 0);

    // Function to get the correct screen position based on area
    const getScreenPosition = () => {
        // Type-safely get the areaId
        const spawn = npc.spawn as {areaId?: string} | undefined;
        const areaId = spawn?.areaId;
        
        if (!areaId) return { x: npc.x || 0, y: npc.y || 0 };

        // Find the area by ID
        const area = areas.find(a => a.id === areaId);
        if (!area) return { x: npc.x || 0, y: npc.y || 0 };

        // Get the offset for this area name
        const offset = AREA_OFFSETS[area.name] || { x: 0, y: 0 };

        // Calculate raw coordinates based on area offset
        let rawX = offset.x + (npc.x || 0);
        let rawY = offset.y + (npc.y || 0);
        
        // Apply boundary constraints - keep NPCs within their respective quadrants
        // Add larger margins to ensure name labels are visible
        const MARGIN = 50; // Increased from 20 to 50 pixels
        
        // Calculate area boundaries
        const minX = offset.x + MARGIN;
        const maxX = offset.x + AREA_WIDTH - MARGIN;
        const minY = offset.y + MARGIN;
        const maxY = offset.y + AREA_HEIGHT - MARGIN;
        
        // Constrain coordinates within boundaries
        const constrainedX = Math.max(minX, Math.min(maxX, rawX));
        const constrainedY = Math.max(minY, Math.min(maxY, rawY));
        
        // Return constrained coordinates
        return {
            x: constrainedX,
            y: constrainedY
        };
    };

    // Effect to handle setting initial position or hard jumps if npc.id changes or area changes
    useEffect(() => {
        if (groupRef.current && isValidPosition) {
            const spawn = npc.spawn as {areaId?: string} | undefined;
            const areaId = spawn?.areaId;
            
            // Do a hard position reset if the NPC has changed areas
            const areaChanged = lastAreaIdRef.current !== areaId;
            if (areaChanged) {
                lastAreaIdRef.current = areaId;
                
                // Stop any running tweens
                if (currentTweenRef.current) {
                    currentTweenRef.current.destroy();
                    currentTweenRef.current = null;
                }
                
                // Hard position reset for area changes
                const position = getScreenPosition();
                groupRef.current.x(position.x);
                groupRef.current.y(position.y);
                setCurrentX(position.x);
                setCurrentY(position.y);
                lastPositionRef.current = position;
            }
        }
    }, [npc.id, npc.spawn, areas, isValidPosition]);

    // Effect to animate to new target npc.x, npc.y from props
    useEffect(() => {
        if (!isValidPosition || !groupRef.current) return;
        
        // Calculate adjusted position based on area offset
        const position = getScreenPosition();
        
        // Check if position has actually changed significantly (use a small threshold to reduce jitter)
        const POSITION_THRESHOLD = 1.0; // Only update if position changed by more than 1px
        const xDiff = Math.abs(position.x - lastPositionRef.current.x);
        const yDiff = Math.abs(position.y - lastPositionRef.current.y);
        
        if (xDiff > POSITION_THRESHOLD || yDiff > POSITION_THRESHOLD) {
            isMovingRef.current = true;
            
            // Stop any existing idle animations
            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
                idleAnimationTimerRef.current = null;
            }
            
            // Stop any running tweens
            if (currentTweenRef.current) {
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
            
            // Animate from current *visual* position to new target position
            const tween = new Konva.Tween({
                node: groupRef.current,
                duration: ANIMATION_DURATION_SECONDS,
                x: position.x,
                y: position.y,
                easing: Konva.Easings.EaseInOut,
                onFinish: () => {
                    // Ensure final position is accurately set
                    if (groupRef.current) {
                        groupRef.current.x(position.x);
                        groupRef.current.y(position.y);
                        lastPositionRef.current = position;
                        isMovingRef.current = false;
                        
                        // Only start idle animations if we're not still moving
                        if (!isMovingRef.current) {
                            startIdleAnimations();
                        }
                    }
                }
            });
            
            currentTweenRef.current = tween;
            tween.play();
            
            return () => {
                if (currentTweenRef.current === tween) {
                    tween.destroy();
                    currentTweenRef.current = null;
                }
            };
        }
    }, [npc.x, npc.y, npc.spawn, areas, isValidPosition]); // Trigger when coordinates or areaId changes

    // Effect to handle idle animations when NPC isn't moving
    useEffect(() => {
        // Start idle animations on mount only if not already moving and position is valid
        if (!isMovingRef.current && isValidPosition) {
            startIdleAnimations();
        }
        
        return () => {
            // Clean up on unmount
            if (idleAnimationTimerRef.current !== null) {
                window.clearTimeout(idleAnimationTimerRef.current);
                idleAnimationTimerRef.current = null;
            }
            
            if (currentTweenRef.current) {
                currentTweenRef.current.destroy();
                currentTweenRef.current = null;
            }
        };
    }, [isValidPosition]);

    const startIdleAnimations = () => {
        // Clear any existing timer
        if (idleAnimationTimerRef.current !== null) {
            window.clearTimeout(idleAnimationTimerRef.current);
            idleAnimationTimerRef.current = null;
        }
        
        // Schedule the next idle animation (using minimal movements)
        idleAnimationTimerRef.current = window.setTimeout(() => {
            // Don't start idle animations if we're in the middle of a real movement
            if (isMovingRef.current || !groupRef.current) {
                startIdleAnimations();
                return;
            }
            
            // Generate random micro-movement within IDLE_MOVEMENT_RANGE
            const offsetX = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
            const offsetY = (Math.random() * 2 - 1) * IDLE_MOVEMENT_RANGE;
            
            // Get the base position stored in lastPositionRef
            const baseX = lastPositionRef.current.x;
            const baseY = lastPositionRef.current.y;
            
            // Animate to the slightly offset position
            const tween = new Konva.Tween({
                node: groupRef.current,
                duration: 0.5, // Quick, subtle movement
                x: baseX + offsetX,
                y: baseY + offsetY,
                easing: Konva.Easings.EaseInOut,
                onFinish: () => {
                    // After moving to offset position, schedule return to base position
                    if (groupRef.current && !isMovingRef.current) {
                        setTimeout(() => {
                            if (groupRef.current && !isMovingRef.current) {
                                // Return to base position
                                const returnTween = new Konva.Tween({
                                    node: groupRef.current,
                                    duration: 0.5,
                                    x: baseX,
                                    y: baseY,
                                    easing: Konva.Easings.EaseInOut,
                                    onFinish: () => {
                                        if (!isMovingRef.current) {
                                            startIdleAnimations(); // Continue the cycle
                                        }
                                    }
                                });
                                
                                currentTweenRef.current = returnTween;
                                returnTween.play();
                            }
                        }, 800); // Small pause at the offset position
                    }
                }
            });
            
            currentTweenRef.current = tween;
            tween.play();
        }, IDLE_MOVEMENT_INTERVAL_MS + Math.random() * 1000); // Add some randomness to the interval
    };

    const handleDotClick = () => {
        if (apiUrl) {
            openNPCDetailModal(npc.id, apiUrl);
        } else {
            console.error("Cannot open NPC details: API URL is not defined.");
            // Optionally push a log to the store: actions.pushLog("Error: Missing API URL for details.");
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
