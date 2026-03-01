import { useState } from 'react';
import BatteryChart from './BatteryChart';

const statusColors = {
  flying: 'bg-green-100 text-green-800',
  idle: 'bg-gray-100 text-gray-800',
  docked: 'bg-blue-100 text-blue-800',
  error: 'bg-red-100 text-red-800',
};

const missionStatusColors = {
  idle: 'text-gray-500',
  en_route: 'text-blue-500',
  on_site: 'text-purple-500',
  returning: 'text-yellow-500',
  aborted: 'text-red-500',
};

function DroneCard({ drone, isSelected, onClick }) {
  const [showChart, setShowChart] = useState(false);
  const telemetry = drone.telemetry;
  const status = drone.status || 'idle';
  const missionStatus = telemetry?.mission_status || 'idle';
  const battery = telemetry?.battery_pct ?? '--';
  
  const getBatteryColor = () => {
    if (battery === '--') return 'bg-gray-200';
    if (battery < 25) return 'bg-red-500';
    if (battery < 50) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  return (
    <div 
      className={`border rounded-lg p-4 cursor-pointer transition-all ${
        isSelected 
          ? 'border-blue-500 shadow-md ring-2 ring-blue-200' 
          : 'border-gray-200 hover:border-gray-300 hover:shadow'
      }`}
      onClick={onClick}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-900 truncate">{drone.name}</h3>
        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColors[status]}`}>
          {status}
        </span>
      </div>

      {/* Model */}
      <p className="text-sm text-gray-500 mb-3">{drone.model}</p>

      {/* Battery Bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="text-gray-600">Battery</span>
          <span className={`font-medium ${
            battery !== '--' && battery < 25 ? 'text-red-600' : 'text-gray-900'
          }`}>
            {battery}%
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div 
            className={`h-2 rounded-full transition-all ${getBatteryColor()}`}
            style={{ width: `${battery}%` }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <span className="text-gray-500">Signal:</span>
          <span className="ml-1 font-medium">
            {telemetry?.signal_strength ?? '--'}%
          </span>
        </div>
        <div>
          <span className="text-gray-500">Altitude:</span>
          <span className="ml-1 font-medium">
            {telemetry?.altitude_m?.toFixed(0) ?? '--'}m
          </span>
        </div>
        <div>
          <span className="text-gray-500">Speed:</span>
          <span className="ml-1 font-medium">
            {telemetry?.speed_mps?.toFixed(1) ?? '--'} m/s
          </span>
        </div>
        <div>
          <span className="text-gray-500">Mission:</span>
          <span className={`ml-1 font-medium ${missionStatusColors[missionStatus]}`}>
            {missionStatus.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Battery History Chart Toggle */}
      {isSelected && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowChart(!showChart);
            }}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            {showChart ? 'Hide' : 'Show'} Battery History
          </button>
          
          {showChart && (
            <div className="mt-2">
              <BatteryChart droneId={drone.id} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default DroneCard;
