import React, { useState, useEffect, useCallback } from 'react';

interface Prompt {
  id: number;
  name: string;
  content: string;
  created_at: string; // Dates will be strings from JSON
  updated_at?: string;
}

const API_BASE_URL = 'http://localhost:8000'; // Ensure this matches your backend API

interface PromptWalletProps {
  isDrawerOpen: boolean;
  onCloseDrawer: () => void;
}

const PromptWallet: React.FC<PromptWalletProps> = ({ isDrawerOpen, onCloseDrawer }) => {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [selectedPromptForModal, setSelectedPromptForModal] = useState<Prompt | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editableContentInModal, setEditableContentInModal] = useState('');

  // Prevent background scroll when drawer or modal is open by handling it on the container
  useEffect(() => {
    const handleWheelEvent = (e: WheelEvent) => {
      if (isDrawerOpen || isModalOpen) {
        const target = e.target as HTMLElement;
        const drawer = document.getElementById('prompt-wallet-drawer');
        const modal = document.getElementById('prompt-wallet-modal');
        
        // Only prevent if we're not scrolling inside the drawer or modal
        if (drawer && !drawer.contains(target) && modal && !modal.contains(target)) {
          e.preventDefault();
        }
      }
    };

    if (isDrawerOpen || isModalOpen) {
      document.addEventListener('wheel', handleWheelEvent, { passive: false });
      return () => document.removeEventListener('wheel', handleWheelEvent);
    }
  }, [isDrawerOpen, isModalOpen]);

  const fetchPromptsInternal = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null); 
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/prompts/`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch prompts');
      }
      const data: Prompt[] = await response.json();
      setPrompts(data);
    } catch (error) {
      if (error instanceof Error) setErrorMessage(error.message);
      console.error('Error fetching prompts:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isDrawerOpen) {
      fetchPromptsInternal();
    }
  }, [isDrawerOpen, fetchPromptsInternal]);

  const handleOpenModalWithPrompt = (prompt: Prompt) => {
    setSelectedPromptForModal(prompt);
    setEditableContentInModal(prompt.content);
    setIsModalOpen(true);
    setSuccessMessage(null);
    setErrorMessage(null);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedPromptForModal(null);
    setEditableContentInModal('');
  };

  const handleSavePromptInModal = async () => {
    if (!selectedPromptForModal) return;
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/prompts/${selectedPromptForModal.name}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: editableContentInModal }),
        }
      );
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update prompt');
      }
      const updatedPromptFromServer: Prompt = await response.json();
      setPrompts(prevPrompts => 
        prevPrompts.map(p => p.id === updatedPromptFromServer.id ? updatedPromptFromServer : p)
      );
      setSelectedPromptForModal(updatedPromptFromServer);
      setEditableContentInModal(updatedPromptFromServer.content);
      setSuccessMessage(`Prompt '${updatedPromptFromServer.name}' saved successfully!`);
      handleCloseModal();
      fetchPromptsInternal(); 
    } catch (error) {
      if (error instanceof Error) setErrorMessage(error.message);
      console.error('Error saving prompt:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Styles
  const overlayStyles: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    zIndex: 9998, // Very high z-index
    opacity: isDrawerOpen ? 1 : 0,
    pointerEvents: isDrawerOpen ? 'auto' : 'none',
    transition: 'opacity 0.3s ease-in-out',
  };

  const drawerStyles: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    right: 0,
    height: '100%',
    width: '100%',
    maxWidth: '340px',
    backgroundColor: '#1f1f1f',
    color: 'white',
    boxShadow: '-4px 0 20px rgba(0, 0, 0, 0.5)',
    zIndex: 9999, // Very high z-index to be above everything
    transform: isDrawerOpen ? 'translateX(0)' : 'translateX(100%)',
    transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    display: 'flex',
    flexDirection: 'column',
  };

  const drawerHeaderStyles: React.CSSProperties = {
    padding: '16px 20px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#171717',
  };

  const closeButtonStyles: React.CSSProperties = {
    backgroundColor: 'transparent',
    border: 'none',
    color: '#999',
    fontSize: '20px',
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: '4px',
    transition: 'all 0.2s ease',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  };

  const promptListStyles: React.CSSProperties = {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px',
    minHeight: 0,
  };

  const promptListContainerStyles: React.CSSProperties = {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    minHeight: 0,
    position: 'relative',
  };

  const promptItemStyles: React.CSSProperties = {
    backgroundColor: '#2a2a2a',
    padding: '14px 16px',
    marginBottom: '8px',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    border: '1px solid rgba(255, 255, 255, 0.05)',
  };

  const promptNameStyles: React.CSSProperties = {
    fontWeight: 500,
    marginBottom: '4px',
    fontSize: '14px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  };

  const promptDateStyles: React.CSSProperties = {
    fontSize: '11px',
    color: '#888',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  };

  const modalOverlayStyles: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    zIndex: 10000, // Even higher for modal
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
  };

  const modalContentStyles: React.CSSProperties = {
    backgroundColor: '#1a1a1a',
    borderRadius: '12px',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.8)',
    padding: '24px',
    width: '100%',
    maxWidth: '600px',
    maxHeight: '90vh',
    display: 'flex',
    flexDirection: 'column',
    color: 'white',
    zIndex: 10001, // Ensure modal content is above overlay
  };

  const modalHeaderStyles: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '20px',
  };

  const textareaStyles: React.CSSProperties = {
    width: '100%',
    padding: '12px',
    backgroundColor: '#2a2a2a',
    border: '1px solid #444',
    borderRadius: '6px',
    color: 'white',
    fontSize: '14px',
    fontFamily: 'monospace',
    resize: 'vertical',
    minHeight: '300px',
  };

  const buttonStyles: React.CSSProperties = {
    padding: '8px 16px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    border: 'none',
  };

  const primaryButtonStyles: React.CSSProperties = {
    ...buttonStyles,
    backgroundColor: '#3b82f6',
    color: 'white',
  };

  const secondaryButtonStyles: React.CSSProperties = {
    ...buttonStyles,
    backgroundColor: '#374151',
    color: 'white',
  };

  return (
    <>
      {/* Drawer - Always render but control visibility with CSS */}
      <div style={overlayStyles} onClick={onCloseDrawer} />
      <div 
        id="prompt-wallet-drawer"
        style={drawerStyles}
      >
        <div style={drawerHeaderStyles}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>Prompt Wallet</h2>
          <button 
            style={closeButtonStyles}
            onClick={onCloseDrawer}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#fff';
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = '#999';
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            ✕
          </button>
        </div>

        {isLoading && prompts.length === 0 && (
          <p style={{ padding: '20px', color: '#666', textAlign: 'center', fontSize: '14px' }}>Loading prompts...</p>
        )}
        
        {errorMessage && !isModalOpen && (
          <div style={{ 
            margin: '12px', 
            padding: '12px', 
            backgroundColor: 'rgba(220, 38, 38, 0.1)', 
            border: '1px solid rgba(220, 38, 38, 0.3)',
            borderRadius: '6px',
            fontSize: '13px',
            color: '#ef4444'
          }}>
            {errorMessage}
          </div>
        )}
        
        {successMessage && !isModalOpen && (
          <div style={{ 
            margin: '12px', 
            padding: '12px', 
            backgroundColor: 'rgba(5, 150, 105, 0.1)', 
            border: '1px solid rgba(5, 150, 105, 0.3)',
            borderRadius: '6px',
            fontSize: '13px',
            color: '#10b981'
          }}>
            {successMessage}
          </div>
        )}

        <div style={promptListContainerStyles}>
          <div style={promptListStyles}>
            {prompts.length > 0 ? (
              prompts.map((prompt) => (
                <div 
                  key={prompt.id}
                  style={promptItemStyles}
                  onClick={() => handleOpenModalWithPrompt(prompt)}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = '#333';
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                    e.currentTarget.style.transform = 'translateX(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = '#2a2a2a';
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)';
                    e.currentTarget.style.transform = 'translateX(0)';
                  }}
                >
                  <div style={promptNameStyles} title={prompt.name}>
                    {prompt.name}
                  </div>
                  <div style={promptDateStyles}>
                    Updated: {formatDate(prompt.updated_at || prompt.created_at)}
                  </div>
                </div>
              ))
            ) : (
              !isLoading && !errorMessage && (
                <p style={{ color: '#666', textAlign: 'center', fontSize: '14px' }}>No prompts found.</p>
              )
            )}
          </div>
        </div>
      </div>

      {/* Modal */}
      {isModalOpen && selectedPromptForModal && (
        <div 
          style={modalOverlayStyles} 
          onClick={handleCloseModal}
        >
          <div 
            id="prompt-wallet-modal"
            style={modalContentStyles} 
            onClick={(e) => e.stopPropagation()}
          >
            <div style={modalHeaderStyles}>
              <h3 style={{ margin: 0, fontSize: '18px' }}>Edit: {selectedPromptForModal.name}</h3>
              <button 
                style={closeButtonStyles}
                onClick={handleCloseModal}
                onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
                onMouseLeave={(e) => e.currentTarget.style.color = '#999'}
              >
                ✕
              </button>
            </div>

            {errorMessage && isModalOpen && (
              <div style={{ marginBottom: '16px', padding: '10px', backgroundColor: '#dc2626', borderRadius: '6px' }}>
                {errorMessage}
              </div>
            )}

            <textarea 
              style={textareaStyles}
              value={editableContentInModal}
              onChange={(e) => setEditableContentInModal(e.target.value)}
              placeholder="Enter prompt content..."
            />

            <div style={{ display: 'flex', gap: '12px', marginTop: '20px', justifyContent: 'flex-end' }}>
              <button 
                style={secondaryButtonStyles}
                onClick={handleCloseModal}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#4b5563'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#374151'}
              >
                Cancel
              </button>
              <button 
                style={{
                  ...primaryButtonStyles,
                  opacity: isLoading || editableContentInModal === selectedPromptForModal.content ? 0.5 : 1,
                }}
                onClick={handleSavePromptInModal}
                disabled={isLoading || editableContentInModal === selectedPromptForModal.content}
                onMouseEnter={(e) => {
                  if (!e.currentTarget.disabled) {
                    e.currentTarget.style.backgroundColor = '#2563eb';
                  }
                }}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#3b82f6'}
              >
                {isLoading ? 'Saving...' : 'Save Prompt'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default PromptWallet; 