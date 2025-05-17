import React from 'react';

export const modalOverlayStyles: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
};

export const modalContentStyles: React.CSSProperties = {
    background: '#2c2c2c',
    color: '#e0e0e0',
    padding: '20px',
    borderRadius: '8px',
    minWidth: '400px',
    maxWidth: '600px',
    maxHeight: '80vh',
    overflowY: 'auto',
    border: '1px solid #444',
    boxShadow: '0 4px 15px rgba(0,0,0,0.2)',
};

export const sectionTitleStyles: React.CSSProperties = {
    marginTop: '15px',
    marginBottom: '8px',
    fontSize: '1.1em',
    color: '#76c7c0',
    borderBottom: '1px solid #444',
    paddingBottom: '5px',
};

export const listItemStyles: React.CSSProperties = {
    padding: '3px 0',
    fontSize: '0.9em',
};

export const tabContainerStyles: React.CSSProperties = {
    display: 'flex',
    borderBottom: '1px solid #444',
    marginBottom: '15px',
};

export const tabStyles: React.CSSProperties = {
    padding: '8px 15px',
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
};

export const activeTabStyles: React.CSSProperties = {
    ...tabStyles,
    borderBottom: '2px solid #76c7c0',
    color: '#76c7c0',
};

export const tagStyles: { [key: string]: React.CSSProperties } = {
    obs: {
        backgroundColor: '#34495e',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    social: {
        backgroundColor: '#3498db',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    environment: {
        backgroundColor: '#2ecc71',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    periodic: {
        backgroundColor: '#9b59b6',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    dialogue: {
        backgroundColor: '#e67e22',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    reflect: {
        backgroundColor: '#e74c3c',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    plan: {
        backgroundColor: '#f1c40f',
        color: 'black',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    },
    other: {
        backgroundColor: '#7f8c8d',
        color: 'white',
        padding: '2px 6px',
        borderRadius: '4px',
        fontSize: '0.7em',
        marginRight: '6px',
    }
};

export const filterButtonStyles = {
    base: {
        padding: '3px 8px',
        margin: '0 4px 8px 0',
        borderRadius: '4px',
        fontSize: '0.8em',
        cursor: 'pointer',
        border: 'none',
    },
    active: {
        opacity: 1,
        fontWeight: 'bold',
    },
    inactive: {
        opacity: 0.6,
    }
}; 