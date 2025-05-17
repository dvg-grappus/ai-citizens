import React from 'react';
import type { ActionInfo } from '../../store/simStore'; // Adjust path as needed
import { sectionTitleStyles, listItemStyles } from '../NPCDetailModal.styles'; // Adjust path for styles

interface ActionsTabProps {
    completedActions: ActionInfo[];
    queuedActions: ActionInfo[];
}

const ActionsTab: React.FC<ActionsTabProps> = ({ completedActions, queuedActions }) => {
    return (
        <>
            <div style={sectionTitleStyles}>Recent Completed Actions:</div>
            {completedActions && completedActions.length > 0 ? (
                <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
                    {completedActions.map((action, index) => (
                        <li key={index} style={listItemStyles}>
                            {action.time} - {action.title}
                            {action.area_name && (
                                <span style={{ color: '#76c7c0' }}> (in {action.area_name})</span>
                            )}
                        </li>
                    ))}
                </ul>
            ) : (
                <p style={listItemStyles}>No completed actions available.</p>
            )}

            <div style={sectionTitleStyles}>Queued Actions ({queuedActions.length}):</div>
            {queuedActions.length > 0 ? (
                <ul style={{ listStyleType: 'none', paddingLeft: 0 }}>
                    {queuedActions.map((action, index) => (
                        <li key={index} style={listItemStyles}>
                            {action.time} - {action.title}
                            {action.area_name && (
                                <span style={{ color: '#76c7c0' }}> (in {action.area_name})</span>
                            )}
                        </li>
                    ))}
                </ul>
            ) : (
                <p style={listItemStyles}>No actions currently queued.</p>
            )}
        </>
    );
};

export default ActionsTab; 