import React from 'react';
import { Button } from '../ui/Button';
import { PixelIcon } from '../ui/PixelIcon';

interface ToolbarProps {
  onAddNode: () => void;
  onSaveSnapshot?: () => void;
  isSaving?: boolean;
  onDeleteSelected?: () => void;
  hasSelection?: boolean;
  onColorChange?: (color: string) => void;
}

export const GraphToolbar: React.FC<ToolbarProps> = ({ 
  onAddNode, 
  onSaveSnapshot, 
  isSaving,
  onDeleteSelected,
  hasSelection,
  onColorChange
}) => {
  return (
    <div className="absolute top-4 right-4 z-10 bg-white p-3 rounded-lg shadow-md border border-gray-200 flex flex-col gap-2 items-stretch min-w-[180px]">
      {/* Color Picker Block */}
      {hasSelection && onColorChange && (
        <div className="flex flex-col gap-2">
          <div className="text-[11px] font-semibold text-gray-600 tracking-wide">Color</div>
          <div className="grid grid-cols-5 gap-2">
            <button onClick={() => onColorChange('blue')} className="w-7 h-7 rounded-full bg-blue-200 hover:ring-2 ring-blue-400 transition-all" title="Blue" />
            <button onClick={() => onColorChange('green')} className="w-7 h-7 rounded-full bg-green-200 hover:ring-2 ring-green-400 transition-all" title="Green" />
            <button onClick={() => onColorChange('yellow')} className="w-7 h-7 rounded-full bg-yellow-200 hover:ring-2 ring-yellow-400 transition-all" title="Yellow" />
            <button onClick={() => onColorChange('red')} className="w-7 h-7 rounded-full bg-red-200 hover:ring-2 ring-red-400 transition-all" title="Red" />
            <button onClick={() => onColorChange('default')} className="w-7 h-7 rounded-full bg-white border border-gray-300 hover:ring-2 ring-gray-400 transition-all" title="Default" />
          </div>
          <div className="border-t border-gray-200 my-1" />
        </div>
      )}

      {/* Actions Stack */}
      <Button variant="secondary" onClick={onAddNode} className="justify-center">
        <span className="flex items-center">
          <PixelIcon name="add" className="w-4 h-4 mr-2" />
          Add Node
        </span>
      </Button>

      {onDeleteSelected && (
        <Button 
          variant="danger" 
          onClick={onDeleteSelected} 
          disabled={!hasSelection}
          className={`justify-center ${!hasSelection ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <span className="flex items-center">
            <PixelIcon name="trash" className="w-4 h-4 mr-2" />
            Delete Selected
          </span>
        </Button>
      )}

      {onSaveSnapshot && (
        <Button variant="primary" onClick={onSaveSnapshot} disabled={isSaving} className="justify-center">
          <span className="flex items-center">
            <PixelIcon name="camera" className="w-4 h-4 mr-2" />
            {isSaving ? 'Saving…' : 'Save & Snapshot'}
          </span>
        </Button>
      )}
    </div>
  );
};