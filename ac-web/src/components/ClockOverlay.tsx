import React from 'react';
import { useSimStore } from '../store/simStore';

const ClockOverlay: React.FC = () => {
    const clock = useSimStore((state) => state.clock);

    const styles: React.CSSProperties = {
        position: 'fixed',
        top: '8px',
        right: '12px',
        color: '#0f0',
        fontFamily: 'monospace',
        fontSize: '12px',
        backgroundColor: 'rgba(0,0,0,0.5)',
        padding: '2px 5px',
        zIndex: 1000,
    };

    const hh = clock.hh.toString().padStart(2, '0');
    const mm = clock.mm.toString().padStart(2, '0');

    return (
        <div style={styles}>
            Day {clock.day} — {hh}:{mm}
        </div>
    );
};

export default ClockOverlay;
