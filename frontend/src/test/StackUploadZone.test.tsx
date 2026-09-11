import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackUploadZone } from '@/components/stacking/StackUploadZone';

function file(name: string): File {
  return new File([new Uint8Array([1])], name, { type: 'image/png' });
}

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) {
    throw new Error('no file input');
  }
  return input;
}

describe('StackUploadZone', () => {
  it('renders a compact "add frames" chip and forwards picked files', () => {
    const onAddFiles = vi.fn();
    const { container } = render(
      <StackUploadZone compact maxSizeMb={100} onAddFiles={onAddFiles} />,
    );

    expect(screen.getByText('Add frames')).toBeInTheDocument();
    fireEvent.change(fileInput(container), { target: { files: [file('a.png')] } });
    expect(onAddFiles).toHaveBeenCalledWith([expect.any(File)]);
  });

  it('renders the full dropzone with the max size hint and opens the picker on click', () => {
    const onAddFiles = vi.fn();
    const { container } = render(
      <StackUploadZone compact={false} maxSizeMb={50} onAddFiles={onAddFiles} />,
    );

    expect(screen.getByText('Drop your light frames here')).toBeInTheDocument();
    expect(screen.getByText(/up to 50 MB each/i)).toBeInTheDocument();

    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click');
    fireEvent.click(screen.getByRole('button', { name: /choose files/i }));
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();

    fireEvent.change(fileInput(container), { target: { files: [file('b.png')] } });
    expect(onAddFiles).toHaveBeenCalledWith([expect.any(File)]);
  });

  it('defaults the max size hint to 100MB when unset', () => {
    render(<StackUploadZone compact={false} onAddFiles={vi.fn()} />);
    expect(screen.getByText(/up to 100 MB each/i)).toBeInTheDocument();
  });

  it('tracks drag state and forwards dropped files', () => {
    const onAddFiles = vi.fn();
    const { container } = render(
      <StackUploadZone compact={false} maxSizeMb={100} onAddFiles={onAddFiles} />,
    );
    const dropzone = container.querySelector('.dropzone');
    if (!dropzone) {
      throw new Error('no dropzone');
    }

    fireEvent.dragOver(dropzone);
    expect(dropzone.className).toContain('dropzone-active');

    fireEvent.dragLeave(dropzone);
    expect(dropzone.className).not.toContain('dropzone-active');

    fireEvent.dragOver(dropzone);
    fireEvent.drop(dropzone, { dataTransfer: { files: [file('dropped.png')] } });
    expect(dropzone.className).not.toContain('dropzone-active');
    expect(onAddFiles).toHaveBeenCalledWith([expect.any(File)]);
  });
});
