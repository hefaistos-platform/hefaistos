import React from 'react';

interface ActivityLog {
    id: string;
    user: { username: string } | null;
    action: string;
    details: string;
    timestamp: string;
}

export const ActivityOverview: React.FC<{ activities: ActivityLog[] }> = ({ activities }) => {
  return (
    <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
       <h2 className="text-xl font-bold mb-4 text-gray-600">Activity Overview</h2>
       <div className="space-y-4 max-h-60 overflow-y-auto pr-2">
           {activities.map((log) => (
               <div key={log.id} className="flex gap-3 text-sm">
                   <div className="text-gray-400 font-mono text-xs w-24 shrink-0">
                       {new Date(log.timestamp).toLocaleDateString()} {new Date(log.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                   </div>
                   <div>
                       <span className="font-bold text-gray-800 mr-2">{log.user?.username || 'System'}</span>
                       <span className={`font-bold text-xs mr-2 px-1 rounded ${
                           log.action === 'APPROVED' ? 'bg-green-100 text-green-800' :
                           log.action === 'REJECTED' ? 'bg-red-100 text-red-800' :
                           'bg-gray-100 text-gray-600'
                       }`}>{log.action}</span>
                       <span className="text-gray-600">{log.details}</span>
                   </div>
               </div>
           ))}
           {activities.length === 0 && <div className="text-gray-400 italic">No activity recorded yet.</div>}
       </div>
    </div>
  );
};
