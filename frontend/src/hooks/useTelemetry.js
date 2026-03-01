import { useState, useEffect, useCallback, useRef } from 'react';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export function useTelemetry() {
  const [drones, setDrones] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [fleetSummary, setFleetSummary] = useState(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const ws = new WebSocket(`${WS_URL}/ws/telemetry`);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        switch (message.type) {
          case 'snapshot':
            handleSnapshot(message.data);
            break;
          case 'telemetry':
            handleTelemetry(message.data);
            break;
          case 'alert':
            handleAlert(message.data);
            break;
          case 'status_change':
            handleStatusChange(message.data);
            break;
          default:
            break;
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
      
      // Attempt to reconnect after 3 seconds
      reconnectTimeoutRef.current = setTimeout(() => {
        console.log('Attempting to reconnect...');
        connect();
      }, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection error');
    };

    wsRef.current = ws;
  }, []);

  const handleSnapshot = useCallback((data) => {
    const droneMap = {};
    
    if (data.drones) {
      data.drones.forEach(({ drone, telemetry }) => {
        droneMap[drone.id] = {
          ...drone,
          telemetry: telemetry
        };
      });
    }
    
    setDrones(droneMap);
    setAlerts(data.alerts || []);
  }, []);

  const handleTelemetry = useCallback((data) => {
    const droneId = data.drone_id;
    
    setDrones(prev => ({
      ...prev,
      [droneId]: {
        ...prev[droneId],
        telemetry: data
      }
    }));
  }, []);

  const handleAlert = useCallback((data) => {
    setAlerts(prev => [data, ...prev].slice(0, 50));
  }, []);

  const handleStatusChange = useCallback((data) => {
    setDrones(prev => ({
      ...prev,
      [data.drone_id]: {
        ...prev[data.drone_id],
        status: data.status
      }
    }));
  }, []);

  const fetchFleetSummary = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/fleet/summary`, {
        headers: {
          'Authorization': 'Bearer dummy-token'
        }
      });
      if (response.ok) {
        const data = await response.json();
        setFleetSummary(data);
      }
    } catch (err) {
      console.error('Error fetching fleet summary:', err);
    }
  }, []);

  useEffect(() => {
    connect();
    
    // Fetch initial fleet summary
    fetchFleetSummary();
    
    // Refresh summary every 10 seconds
    const interval = setInterval(fetchFleetSummary, 10000);
    
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
      clearInterval(interval);
    };
  }, [connect, fetchFleetSummary]);

  const subscribe = useCallback((droneIds) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ subscribe: droneIds }));
    }
  }, []);

  const unsubscribe = useCallback((droneIds) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ unsubscribe: droneIds }));
    }
  }, []);

  return {
    drones,
    alerts,
    fleetSummary,
    connected,
    error,
    subscribe,
    unsubscribe,
    refreshSummary: fetchFleetSummary
  };
}

export default useTelemetry;
