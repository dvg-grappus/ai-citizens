import React from 'react';
import { sectionTitleStyles, listItemStyles } from '../NPCDetailModal.styles'; // Adjust path for styles

interface PlanTabProps {
    currentPlanSummary: string[];
}

const PlanTab: React.FC<PlanTabProps> = ({ currentPlanSummary }) => {
    return (
        <>
            <div style={sectionTitleStyles}>Current Day's Plan Summary:</div>
            {currentPlanSummary.length > 0 ? (
                <ul style={{ listStyleType: 'decimal', paddingLeft: '20px' }}>
                    {currentPlanSummary.map((actionStr, index) => (
                        <li key={index} style={listItemStyles}>{actionStr}</li>
                    ))}
                </ul>
            ) : (
                <p style={listItemStyles}>No plan summary available for the current day.</p>
            )}
        </>
    );
};

export default PlanTab; 