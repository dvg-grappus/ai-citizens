import React from 'react';
import type { ReflectionInfo } from '../../store/simStore'; // Adjust path as needed
import { sectionTitleStyles, listItemStyles } from '../NPCDetailModal.styles'; // Adjust path for styles

interface ReflectionsTabProps {
    reflections: ReflectionInfo[];
}

const ReflectionsTab: React.FC<ReflectionsTabProps> = ({ reflections }) => {
    return (
        <>
            <div style={sectionTitleStyles}>Recent Reflections:</div>
            {reflections && reflections.length > 0 ? (
                <div>
                    {reflections.map((reflection, index) => (
                        <div key={index} style={{ marginBottom: '15px' }}>
                            {reflection.time && (
                                <div style={{ fontWeight: 'bold', fontSize: '0.8em', color: '#76c7c0', marginBottom: '3px' }}>
                                    {reflection.time}
                                </div>
                            )}
                            <div style={{...listItemStyles, whiteSpace: 'pre-wrap'}}>{reflection.content}</div>
                        </div>
                    ))}
                </div>
            ) : (
                <p style={listItemStyles}>No reflections available.</p>
            )}
        </>
    );
};

export default ReflectionsTab; 