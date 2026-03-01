import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useEffect } from 'react';

// Custom marker icons
const createIcon = (color) => L.divIcon({
  className: 'custom-marker',
  html: `<div style="
    background-color: ${color};
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 3px solid white;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
  "></div>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
});

const icons = {
  flying: createIcon('#22c55e'),   // green
  idle: createIcon('#6b7280'),     // gray
  docked: createIcon('#3b82f6'),    // blue
  error: createIcon('#ef4444'),      // red
};

function MapUpdater({ center }) {
  const map = useMap();
  
  useEffect(() => {
    if (center) {
      map.flyTo([center.lat, center.lng], 14, {
        duration: 1
      });
    }
  }, [center, map]);
  
  return null;
}

function FleetMap({ drones, onDroneClick, selectedDrone }) {
  const defaultCenter = [18.5204, 73.8567]; // Pune, India
  const defaultZoom = 13;

  // Find center of all drones or use default
  const getCenter = () => {
    if (drones.length === 0) return defaultCenter;
    
    const flyingDrones = drones.filter(d => 
      d.telemetry && (d.status === 'flying' || d.telemetry.mission_status === 'en_route')
    );
    
    if (flyingDrones.length > 0 && flyingDrones[0].telemetry) {
      return [flyingDrones[0].telemetry.lat, flyingDrones[0].telemetry.lng];
    }
    
    return defaultCenter;
  };

  const selectedDroneData = selectedDrone 
    ? drones.find(d => d.id === selectedDrone) 
    : null;

  return (
    <div style={{ height: '400px', width: '100%' }}>
      <MapContainer
        center={getCenter()}
        zoom={defaultZoom}
        style={{ height: '100%', width: '100%' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        
        {selectedDroneData?.telemetry && (
          <MapUpdater center={selectedDroneData.telemetry} />
        )}
        
        {drones.map(drone => {
          if (!drone.telemetry) return null;
          
          const status = drone.status || 'idle';
          const icon = icons[status] || icons.idle;
          
          return (
            <Marker
              key={drone.id}
              position={[drone.telemetry.lat, drone.telemetry.lng]}
              icon={icon}
              eventHandlers={{
                click: () => onDroneClick(drone.id)
              }}
            >
              <Popup>
                <div className="text-sm">
                  <div className="font-semibold">{drone.name}</div>
                  <div className="text-gray-600">Model: {drone.model}</div>
                  <div className="text-gray-600">Status: {status}</div>
                  <div className="text-gray-600">Battery: {drone.telemetry.battery_pct}%</div>
                  <div className="text-gray-600">Altitude: {drone.telemetry.altitude_m}m</div>
                  <div className="text-gray-600">Speed: {drone.telemetry.speed_mps} m/s</div>
                  <div className="text-gray-600">Signal: {drone.telemetry.signal_strength}%</div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}

export default FleetMap;
