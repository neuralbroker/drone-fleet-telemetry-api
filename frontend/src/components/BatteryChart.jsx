import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:9001';

function BatteryChart({ droneId, authHeaders }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const res = await fetch(`${API_URL}/fleet/${droneId}/telemetry/history?limit=60`, {
          headers: authHeaders()
        });
        if (res.ok) {
          const result = await res.json();
          const chartData = (result.telemetry || []).map((frame) => ({
            time: new Date(frame.timestamp).toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit'
            }),
            battery: frame.battery_pct
          }));
          setData(chartData.reverse());
        }
      } catch (err) {
        console.error('Error fetching telemetry history:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
    const interval = setInterval(fetchHistory, 5000);
    return () => clearInterval(interval);
  }, [droneId, authHeaders]);

  if (loading) {
    return <div className="h-32 flex items-center justify-center text-gray-400 text-sm">Loading...</div>;
  }

  if (data.length === 0) {
    return <div className="h-32 flex items-center justify-center text-gray-400 text-sm">No history yet</div>;
  }

  return (
    <div className="h-32">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10 }}
          />
          <Tooltip
            contentStyle={{
              fontSize: '12px',
              borderRadius: '4px',
              border: 'none',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
            }}
          />
          <Line
            type="monotone"
            dataKey="battery"
            stroke="#22c55e"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default BatteryChart;