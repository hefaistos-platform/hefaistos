import React, { useState } from 'react'; // Added useState
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { message, Input, Button, Space, List, Tag, Modal, Typography } from 'antd';

// Removed dependency on deprecated PlaybookDetailPage query

// NOTE: You should replace these placeholder types with your actual defined types
interface AuthorType {
  username: string;
}

// Renamed Task to TaskType to match PlaybookDetailPage.tsx prop
interface TaskType { 
  id: string;
  title: string;
  status: 'TODO' | 'IN_PROGRESS' | 'DONE'; // Include all backend statuses
  assignee: AuthorType | null;
}

interface TaskManagerProps {
  playbookId: string;
  tasks: TaskType[]; // Expects an array of TaskType
}

// --- GraphQL Mutations ---

const CREATE_TASK_MUTATION = gql`
  mutation CreateTask($playbookId: UUID!, $title: String!) {
    createTask(playbookId: $playbookId, title: $title) {
      task { id }
    }
  }
`;

const UPDATE_TASK_MUTATION = gql`
  mutation UpdateTask($taskId: ID!, $status: String) {
    updateTask(taskId: $taskId, status: $status) {
      task { id status }
    }
  }
`;

const DELETE_TASK_MUTATION = gql`
  mutation DeleteTask($taskId: ID!) {
    deleteTask(taskId: $taskId) {
      ok
    }
  }
`;

// --- Component ---

export const TaskManager: React.FC<TaskManagerProps> = ({ playbookId, tasks }) => {
  // Correctly destructure useState, defining state variable and setter
  const [newTaskTitle, setNewTaskTitle] = useState('');

  // Setup mutations with proper destructuring and refetch logic
  const [createTask, { loading: createLoading }] = useMutation(CREATE_TASK_MUTATION);

  const [updateTask, { loading: updateLoading }] = useMutation(UPDATE_TASK_MUTATION);
  
  const [deleteTask, { loading: deleteLoading }] = useMutation(DELETE_TASK_MUTATION);

  const handleAddTask = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!newTaskTitle.trim()) return;
    try {
      await createTask({ variables: { playbookId, title: newTaskTitle } });
      message.success('Task added');
      setNewTaskTitle('');
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
      message.error('Failed to add task');
    }
  };

  const handleToggleStatus = async (task: TaskType) => {
    const newStatus = task.status === 'DONE' ? 'TODO' : 'DONE';
    try {
      await updateTask({ variables: { taskId: task.id, status: newStatus } });
      message.success('Task status updated');
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e);
      message.error('Failed to update task');
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    Modal.confirm({
      title: 'Delete task?',
      content: 'This action cannot be undone.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await deleteTask({ variables: { taskId } });
          message.success('Task deleted');
        } catch (e) {
          // eslint-disable-next-line no-console
          console.error(e);
          message.error('Failed to delete task');
        }
      }
    });
  };

  return (
    <div>
      <form onSubmit={handleAddTask} style={{ marginBottom: 16 }}>
        <Space>
          <Input
            value={newTaskTitle}
            onChange={(e) => setNewTaskTitle(e.target.value)}
            placeholder="Add a new task..."
            disabled={createLoading}
          />
          <Button htmlType="submit" type="primary" disabled={createLoading || !newTaskTitle.trim()} loading={createLoading}>
            Add Task
          </Button>
        </Space>
      </form>
      {tasks.length === 0 ? (
        <Typography.Text type="secondary">No tasks for this playbook yet.</Typography.Text>
      ) : (
        <List
          dataSource={tasks}
          renderItem={(task) => (
            <List.Item
              key={task.id}
              actions={[
                <Button size="small" onClick={() => handleToggleStatus(task)} loading={updateLoading}>
                  {task.status === 'DONE' ? 'Mark To-Do' : 'Mark Done'}
                </Button>,
                <Button danger size="small" onClick={() => handleDeleteTask(task.id)} loading={deleteLoading}>
                  Delete
                </Button>
              ]}
            >
              <Space direction="vertical">
                <span style={{ textDecoration: task.status === 'DONE' ? 'line-through' : 'none' }}>{task.title}</span>
                <Space>
                  <Tag color={task.status === 'DONE' ? 'green' : 'default'}>{task.status}</Tag>
                  <Tag color="default">Assignee: {task.assignee?.username || 'None'}</Tag>
                </Space>
              </Space>
            </List.Item>
          )}
        />
      )}
    </div>
  );
};
