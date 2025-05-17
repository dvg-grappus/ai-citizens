import json
from typing import List, Any, Dict

_ws_clients: List[Any] = []

def register_ws(ws: Any):
    # Ensure client is not already registered before appending
    if ws not in _ws_clients:
        _ws_clients.append(ws)
    # print(f"WS Registered. Total clients: {len(_ws_clients)}") # Optional debug

def unregister_ws(ws: Any):
    if ws in _ws_clients:
        _ws_clients.remove(ws)
    # print(f"WS Unregistered. Total clients: {len(_ws_clients)}") # Optional debug

async def broadcast_ws_message(message_type: str, data: Dict):
    typed_payload = {"type": message_type, "data": data}
    # print(f"Broadcasting WS: {json.dumps(typed_payload)}") # Optional: for deep debugging
    
    # Iterate over a copy of the list for safe removal
    active_clients_after_send = []
    for ws_client in list(_ws_clients): # Iterate over a copy
        if ws_client:
            try:
                await ws_client.send_text(json.dumps(typed_payload))
                active_clients_after_send.append(ws_client) # Keep if send was successful
            except Exception as e:
                print(f"Error sending WS message ({message_type}) to client {ws_client}: {e} - Removing client.")
                # No need to explicitly remove here if we rebuild the list with active_clients_after_send
        else:
            print(f"Found a None WebSocket object in _ws_clients during {message_type} broadcast")
            # This client will be filtered out when rebuilding _ws_clients

    _ws_clients[:] = active_clients_after_send # Update the original list with active clients 