import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function BatteryChart({ droneId }) {
  const [data, setData] = useState([]);

  useEffect(() => {
    // Generate sample battery history data
    // In production, this would come from the API
    const history = [];
    const now = Date.now();
    
    for (let i = 60; i >= 0; i--) {
      history.push({
        time: new Date(now - i * 1000).toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit'
        }),
        battery: Math.max(5, 100 - (60 - i) * 1.5 + Math.random() * 5)
      });
    }
    
    setData(history);
  }, [droneId]);

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
