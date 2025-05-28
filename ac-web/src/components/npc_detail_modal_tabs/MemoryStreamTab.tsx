import React, { useState, useMemo } from 'react';
import type { MemoryEvent } from '../../store/simStore'; // Adjust path as needed
import {
    sectionTitleStyles,
    listItemStyles,
    tagStyles,
    filterButtonStyles,
    viewTranscriptButtonStyles
} from '../NPCDetailModal.styles'; // Adjust path for styles
import DialogueTranscriptModal from './DialogueTranscriptModal';

interface MemoryStreamTabProps {
    memoryStream: MemoryEvent[];
}

// Helper function to determine memory type from content and type property
const getMemoryType = (memory: MemoryEvent): string => {
    if (memory.type === 'reflect') return 'reflect';
    if (memory.type === 'plan') return 'plan';
    if (memory.type === 'replan') return 'replan';
    if (memory.type === 'dialogue_summary') return 'dialogue_summary';
    if (memory.type === 'obs') {
        const content = memory.content || '';
        if (content.includes('[Social]')) return 'social';
        if (content.includes('[Environment]')) return 'environment';
        if (content.includes('[Periodic]')) return 'periodic';
        if (content.includes('[Dialogue]')) return 'dialogue';
        return 'other'; // Default for obs if no specific tag
    }
    return memory.type || 'other'; // Fallback for non-obs types or if type is missing
};

// Helper function to clean memory content by removing tags
const cleanMemoryContent = (content: string): string => {
    return content
        .replace(/\[Social\]/g, '')
        .replace(/\[Environment\]/g, '')
        .replace(/\[Periodic\]/g, '')
        .replace(/\[Dialogue\]/g, '')
        .trim();
};

const MemoryStreamTab: React.FC<MemoryStreamTabProps> = ({ memoryStream }) => {
    const [activeFilter, setActiveFilter] = useState('all');
    const [isTranscriptModalOpen, setIsTranscriptModalOpen] = useState(false);
    const [selectedDialogueId, setSelectedDialogueId] = useState<string | null>(null);

    const filteredMemoryStream = useMemo(() => {
        if (!memoryStream) return [];
        const sortedStream = [...memoryStream].sort((a, b) => (b.sim_min || 0) - (a.sim_min || 0));

        if (activeFilter === 'all') {
            return sortedStream;
        }
        return sortedStream.filter(memory => {
            const type = getMemoryType(memory);
            return type === activeFilter;
        });
    }, [memoryStream, activeFilter]);

    const filterTypes = ['all', 'social', 'environment', 'periodic', 'dialogue_summary', 'reflect', 'plan', 'replan', 'other'];

    const handleViewTranscript = (dialogueId: string) => {
        setSelectedDialogueId(dialogueId);
        setIsTranscriptModalOpen(true);
    };

    return (
        <>
            <div style={sectionTitleStyles}>Memory Stream (Recent Events):</div>

            <div style={{ marginBottom: '12px' }}>
                {filterTypes.map(filterType => {
                    const buttonStyle: React.CSSProperties = {
                        ...filterButtonStyles.base,
                        ...(activeFilter === filterType ? filterButtonStyles.active : filterButtonStyles.inactive),
                    };
                    if (filterType === 'all') {
                        buttonStyle.backgroundColor = '#555';
                        buttonStyle.color = 'white';
                    } else {
                        const typeSpecificTagStyle = tagStyles[filterType as keyof typeof tagStyles];
                        if (typeSpecificTagStyle) {
                            Object.assign(buttonStyle, typeSpecificTagStyle);
                        }
                    }

                    return (
                        <button
                            key={filterType}
                            onClick={() => setActiveFilter(filterType)}
                            style={buttonStyle}
                        >
                            {filterType === 'dialogue_summary' ? 'Dialogue' : filterType.charAt(0).toUpperCase() + filterType.slice(1)}
                        </button>
                    );
                })}
            </div>

            {filteredMemoryStream.length > 0 ? (
                <div>
                    {filteredMemoryStream.map((memory, index) => {
                        const memoryType = getMemoryType(memory);
                        const cleanContent = cleanMemoryContent(memory.content);
                        console.log('[MemoryStreamTab] Rendering memory item:', memory);

                        return (
                            <div key={index} style={{ marginBottom: '12px', borderBottom: index < filteredMemoryStream.length - 1 ? '1px solid #444' : 'none', paddingBottom: '8px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '3px' }}>
                                    <div style={{ fontWeight: 'bold', fontSize: '0.8em', color: '#76c7c0' }}>
                                        {memory.time || 'Unknown time'}
                                    </div>
                                    <div>
                                        {memoryType === 'reflect' || memoryType === 'plan' || memoryType === 'replan' || memoryType === 'dialogue_summary' ? (
                                            <span style={tagStyles[memoryType as keyof typeof tagStyles] || tagStyles.other}>
                                                {memoryType === 'dialogue_summary' ? 'Dialogue' : memoryType.charAt(0).toUpperCase() + memoryType.slice(1)}
                                            </span>
                                        ) : (
                                            <>
                                                <span style={tagStyles.obs}>obs</span>
                                                {tagStyles[memoryType as keyof typeof tagStyles] && (
                                                    <span style={tagStyles[memoryType as keyof typeof tagStyles]}>
                                                        {memoryType.charAt(0).toUpperCase() + memoryType.slice(1)}
                                                    </span>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </div>
                                <div style={{...listItemStyles, whiteSpace: 'pre-wrap'}}>{cleanContent}</div>
                                {memory.type === 'dialogue_summary' && memory.metadata?.dialogue_id && (
                                    <button 
                                        onClick={() => handleViewTranscript(memory.metadata!.dialogue_id!)}
                                        style={viewTranscriptButtonStyles}
                                    >
                                        View Transcript
                                    </button>
                                )}
                            </div>
                        );
                    })}
                </div>
            ) : (
                <p style={listItemStyles}>No memory events available or all types filtered out.</p>
            )}
            {selectedDialogueId && (
                <DialogueTranscriptModal 
                    isOpen={isTranscriptModalOpen} 
                    onClose={() => setIsTranscriptModalOpen(false)}
                    dialogueId={selectedDialogueId}
                />
            )}
        </>
    );
};

export default MemoryStreamTab; 