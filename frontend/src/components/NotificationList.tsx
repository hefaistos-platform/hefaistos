import React from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import { Link } from 'react-router-dom';
import { Button } from 'antd';

// Queries and Mutations from Day 92
const MY_NOTIFICATIONS_QUERY = gql`
  query GetMyNotifications {
    myNotifications {
      id
      verb
      read
      timestamp
      actor { username }
      target {
        ... on PlaybookType {
          id
          title
        }
      }
    }
  }
`;

const MARK_READ_MUTATION = gql`
  mutation MarkRead($id: UUID!) {
    markNotificationAsRead(id: $id) {
      notification { id, read }
    }
  }
`;

// --- TypeScript Types ---
interface Actor { username: string; }
interface Target { id: string; title: string; }
interface Notification {
  id: string;
  verb: string;
  read: boolean;
  timestamp: string;
  actor: Actor | null;
  target: Target | null;
}

interface GetMyNotificationsData {
  myNotifications: Notification[];
}

interface NotificationListProps {
  onClose: () => void;
  onNotificationRead: () => void; // Function to refetch the unread count
}

export const NotificationList: React.FC<NotificationListProps> = ({ onClose, onNotificationRead }) => {
  const { data, loading, error } = useQuery<GetMyNotificationsData>(MY_NOTIFICATIONS_QUERY, {
    fetchPolicy: 'network-only', // Always get the latest
  });
  const [markAsRead] = useMutation(MARK_READ_MUTATION);

  const handleMarkAsRead = (id: string) => {
    markAsRead({ variables: { id } })
      .then(() => {
        onNotificationRead(); // Refetch the count in the parent
      })
      .catch((e: unknown) => console.error("Failed to mark as read:", e));
  };

  return (
    <div className="max-h-96 overflow-y-auto">
      {loading && <p className="p-4 text-gray-500">Loading...</p>}
      {error && <p className="p-4 text-hefaistos-accent-red">Error: {error.message}</p>}

      {data?.myNotifications.length === 0 && (
        <p className="p-4 text-gray-500">You have no notifications.</p>
      )}

      <ul className="divide-y divide-hefaistos-border">
        {data?.myNotifications.map((n: Notification) => (
          <li key={n.id} className={`p-3 ${n.read ? 'opacity-60' : 'bg-blue-50'}`}>
            <div className="text-sm">
              <strong>{n.actor?.username || 'System'}</strong> {n.verb}
              {n.target ? (
                <Link 
                  to={`/playbooks/${n.target.id}`} 
                  onClick={onClose} 
                  className="font-bold text-hefaistos-primary hover:underline"
                >
                  {n.target.title}
                </Link>
              ) : (
                'an item'
              )}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {new Date(n.timestamp).toLocaleString()}
              {!n.read && (
                <Button 
                  type="primary" 
                  onClick={() => handleMarkAsRead(n.id)}
                  size="small"
                >
                  Mark as Read
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
};