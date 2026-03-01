const severityStyles = {
  warning: 'border-l-yellow-500 bg-yellow-50',
  critical: 'border-l-red-500 bg-red-50',
};

const alertTypeLabels = {
  low_battery: 'Low Battery',
  gps_deviation: 'GPS Deviation',
  signal_loss: 'Signal Loss',
  mission_abort: 'Mission Abort',
};

function AlertFeed({ alerts }) {
  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className="bg-white rounded-lg shadow p-4 h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">Alert Feed</h2>
        <span className="text-sm text-gray-500">
          {alerts.length} recent
        </span>
      </div>
      
      <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto">
        {alerts.length === 0 ? (
          <p className="text-gray-500 text-center py-8">
            No alerts
          </p>
        ) : (
          alerts.map((alert, index) => (
            <div
              key={`${alert.id}-${index}`}
              className={`border-l-4 p-3 rounded-r ${severityStyles[alert.severity]}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      alert.severity === 'critical'
                        ? 'bg-red-200 text-red-800'
                        : 'bg-yellow-200 text-yellow-800'
                    }`}>
                      {alert.severity.toUpperCase()}
                    </span>
                    <span className="text-xs text-gray-500">
                      {alertTypeLabels[alert.type] || alert.type}
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 mt-1">
                    {alert.message}
                  </p>
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-2">
                {alert.timestamp ? formatTime(alert.timestamp) : 'Just now'}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default AlertFeed;
