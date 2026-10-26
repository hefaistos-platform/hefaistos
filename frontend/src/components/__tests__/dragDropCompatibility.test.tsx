import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DragDropContext, Draggable, Droppable } from '@hello-pangea/dnd';

it('supports keyboard drag and drop with React 19 in StrictMode', async () => {
  const onDragStart = jest.fn();
  const onDragEnd = jest.fn();
  const bounds = jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
    .mockImplementation(function (this: HTMLElement) {
      const top = this.dataset.testid === 'second' ? 40 : 0;
      const height = this.dataset.testid === 'list' ? 80 : 40;
      return { x: 0, y: top, left: 0, top, right: 200, bottom: top + height,
        width: 200, height, toJSON: () => ({}) };
    });

  try {
    render(
      <React.StrictMode>
        <DragDropContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
          <Droppable droppableId="board">
            {(provided) => (
              <div ref={provided.innerRef} {...provided.droppableProps} data-testid="list">
                {['first', 'second'].map((id, index) => (
                  <Draggable key={id} draggableId={id} index={index}>
                    {(item) => (
                      <div ref={item.innerRef} {...item.draggableProps}
                        {...item.dragHandleProps} data-testid={id}>{id}</div>
                    )}
                  </Draggable>
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>
      </React.StrictMode>,
    );

    const first = screen.getByTestId('first');
    first.focus();
    fireEvent.keyDown(first, { keyCode: 32, key: ' ' });
    await waitFor(() => expect(onDragStart).toHaveBeenCalled());
    fireEvent.keyDown(first, { keyCode: 40, key: 'ArrowDown' });
    fireEvent.keyDown(first, { keyCode: 32, key: ' ' });
    await waitFor(() => expect(onDragEnd).toHaveBeenCalledWith(expect.objectContaining({
      reason: 'DROP', draggableId: 'first',
      source: { droppableId: 'board', index: 0 },
      destination: { droppableId: 'board', index: 1 },
    }), expect.anything()));
  } finally {
    bounds.mockRestore();
  }
});
