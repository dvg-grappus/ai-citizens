import React from 'react';
import { Stage, Layer, Rect, Circle, Text as KonvaText, Group } from 'react-konva';
import { useSimStore, DisplayNPC, DisplayArea } from '../store/simStore';

const CanvasStage: React.FC = () => {
    const npcs = useSimStore((state) => state.npcs);
    const areas = useSimStore((state) => state.areas);

    // Type guard for Area bounds
    const hasValidBounds = (bounds: any): bounds is { x: number; y: number; w: number; h: number } => {
        return bounds && 
               typeof bounds.x === 'number' && typeof bounds.y === 'number' &&
               typeof bounds.w === 'number' && typeof bounds.h === 'number';
    };

    return (
        <Stage width={420} height={420} style={{ backgroundColor: 'black' }}>
            <Layer> {/* Areas Layer */}
                {areas.map((area: DisplayArea) => {
                    if (!hasValidBounds(area.bounds)) return null; // Skip rendering if bounds are not valid
                    return (
                        <Rect
                            key={area.id}
                            x={area.bounds.x}
                            y={area.bounds.y}
                            width={area.bounds.w}
                            height={area.bounds.h}
                            stroke="#fff"
                            strokeWidth={1}
                        />
                    );
                })}
            </Layer>
            <Layer> {/* NPCs Layer */}
                {npcs.map((npc: DisplayNPC) => (
                    <Group key={npc.id} x={npc.x} y={npc.y}>
                        <Circle radius={4} fill="#fff" />
                        {npc.emoji && (
                            <KonvaText
                                text={npc.emoji}
                                fontSize={10}
                                x={-5} // Adjust for emoji centering
                                y={-14} // Adjust for emoji positioning
                                fill="#fff" // Ensure emoji is visible
                            />
                        )}
                        {npc.name && (
                             <KonvaText
                                text={npc.name}
                                fontSize={6}
                                fill="#ccc"
                                y={8}
                                offsetX={(npc.name.length * 6 * 0.5) / 2} // Basic centering for name
                            />
                        )}
                    </Group>
                ))}
            </Layer>
        </Stage>
    );
};

export default CanvasStage; 