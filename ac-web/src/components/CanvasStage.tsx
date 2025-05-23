import React, { useEffect, useState } from 'react';
import { Stage, Layer, Rect, Text as KonvaText } from 'react-konva';
import { useSimStore } from '../store/simStore';
import type { DisplayNPC, DisplayArea } from '../store/simStore';
import NPCDot from './NPCDot';
import {
    STAGE_WIDTH,
    STAGE_HEIGHT,
    AREA_WIDTH,
    AREA_HEIGHT,
} from '../constants';

// Function to get a color based on NPC ID or name (simple hash for variety)
const getNPCColor = (id: string): string => {
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
        hash = id.charCodeAt(i) + ((hash << 5) - hash);
        hash = hash & hash; // Convert to 32bit integer
    }
    const color = (hash & 0x00FFFFFF).toString(16).toUpperCase();
    return "#" + "000000".substring(0, 6 - color.length) + color;
};

// Define how the 4 areas are laid out within this stage
const AREA_LAYOUT = {
    rows: 2,
    cols: 2,
};

interface DefinedArea {
    id: string;
    name: string;
    bounds: { x: number; y: number; w: number; h: number }; // Explicit bounds structure
}

const CanvasStage: React.FC = () => {
    const npcs = useSimStore((state) => state.npcs);
    const areasFromStore = useSimStore((state) => state.areas); // Now using areas from store
    const [areasWithBounds, setAreasWithBounds] = useState<DefinedArea[]>([]);

    // Define the proper area locations based on names
    useEffect(() => {
        if (areasFromStore && areasFromStore.length > 0) {
            // Create area definitions that map ACTUAL area IDs from database to their visual positions
            const newAreasWithBounds: DefinedArea[] = areasFromStore.map(area => {
                let bounds;
                
                // Map by name instead of assuming IDs
                switch (area.name) {
                    case 'Bedroom':
                        bounds = { x: 0, y: 0, w: AREA_WIDTH, h: AREA_HEIGHT };
                        break;
                    case 'Office':
                        bounds = { x: AREA_WIDTH, y: 0, w: AREA_WIDTH, h: AREA_HEIGHT };
                        break;
                    case 'Bathroom':
                        bounds = { x: 0, y: AREA_HEIGHT, w: AREA_WIDTH, h: AREA_HEIGHT };
                        break;
                    case 'Lounge':
                        bounds = { x: AREA_WIDTH, y: AREA_HEIGHT, w: AREA_WIDTH, h: AREA_HEIGHT };
                        break;
                    default:
                        bounds = { x: 0, y: 0, w: AREA_WIDTH, h: AREA_HEIGHT };
                }
                
                return {
                    id: area.id, // Use the ACTUAL ID from database
                    name: area.name,
                    bounds
                };
            });
            
            setAreasWithBounds(newAreasWithBounds);
        }
    }, [areasFromStore]);

    return (
        <Stage width={STAGE_WIDTH} height={STAGE_HEIGHT} style={{ backgroundColor: '#202020' }}> 
            <Layer> 
                {areasWithBounds.map((area) => (
                    <React.Fragment key={`area_group_${area.id}`}>
                        <Rect
                            x={area.bounds.x}
                            y={area.bounds.y}
                            width={area.bounds.w}
                            height={area.bounds.h}
                            stroke="#444"
                            strokeWidth={1}
                            fill="#282828"
                        />
                        <KonvaText 
                            text={`${area.name} (${area.id.substring(0, 4)}...)`}
                            x={area.bounds.x + 10}
                            y={area.bounds.y + 10}
                            fontSize={12}
                            fill="#888"
                        />
                    </React.Fragment>
                ))}
            </Layer>
            <Layer> 
                {npcs.map((npc: DisplayNPC) => (
                    <NPCDot key={npc.id} npc={npc} color={getNPCColor(npc.id)} />
                ))}
            </Layer>
        </Stage>
    );
};

export default CanvasStage;
