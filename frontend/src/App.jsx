import { useState } from 'react';
import useTelemetry from './hooks/useTelemetry';
import FleetMap from './components/FleetMap';
import DroneCard from './components/DroneCard';
import AlertFeed from './components/AlertFeed';

function App() {
  const { drones, alerts, fleetSummary, connected } = useTelemetry();
  const [selectedDrone, setSelectedDrone] = useState(null);

  const droneList = Object.values(drones);

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <h1 className="text-2xl font-bold text-gray-900">
                Drone Fleet Telemetry
              </h1>
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                connected 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-red-100 text-red-800'
              }`}>
                {connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            
            {/* Fleet Summary Stats */}
            {fleetSummary && (
              <div className="flex items-center space-x-6 text-sm">
                <div className="flex items-center space-x-2">
                  <span className="text-gray-500">Total:</span>
                  <span className="font-semibold">{fleetSummary.total_drones}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-gray-500">Active:</span>
                  <span className="font-semibold text-green-600">{fleetSummary.active_drones}</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-gray-500">Avg Battery:</span>
                  <span className="font-semibold">{fleetSummary.average_battery_pct}%</span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-gray-500">Alerts:</span>
                  <span className={`font-semibold ${
                    fleetSummary.recent_alerts_count > 0 ? 'text-yellow-600' : 'text-gray-600'
                  }`}>
                    {fleetSummary.recent_alerts_count}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Map and Drones */}
          <div className="lg:col-span-2 space-y-6">
            {/* Fleet Map */}
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Live Fleet Map</h2>
              <FleetMap 
                drones={droneList} 
                onDroneClick={setSelectedDrone}
                selectedDrone={selectedDrone}
              />
            </div>

            {/* Drone Cards Grid */}
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Drone Status ({droneList.length})
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {droneList.map(drone => (
                  <DroneCard
                    key={drone.id}
                    drone={drone}
                    isSelected={selectedDrone === drone.id}
                    onClick={() => setSelectedDrone(drone.id)}
                  />
                ))}
              </div>
              {droneList.length === 0 && (
                <p className="text-gray-500 text-center py-8">
                  Waiting for drone data...
                </p>
              )}
            </div>
          </div>

          {/* Right Column - Alert Feed */}
          <div className="lg:col-span-1">
            <AlertFeed alerts={alerts} />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
