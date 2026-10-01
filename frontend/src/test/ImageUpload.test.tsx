import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImageUpload } from '@/components/ImageUpload';

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement;
}

describe('ImageUpload', () => {
  it('renders the file picker and the configured size limit', () => {
    render(<ImageUpload onUpload={vi.fn()} maxSizeMb={250} />);

    expect(screen.getByRole('button', { name: /choose a photo/i })).toBeInTheDocument();
    expect(screen.getByText(/up to 250 MB/i)).toBeInTheDocument();
  });

  it('rejects a file over the configured size limit with that number', () => {
    const onUpload = vi.fn();
    render(<ImageUpload onUpload={onUpload} maxSizeMb={10} />);
    const big = new File([new Uint8Array(11 * 1024 * 1024)], 'huge.fits');

    fireEvent.change(fileInput(), { target: { files: [big] } });

    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/larger than the 10 MB limit/i)).toBeInTheDocument();
  });

  it('shows an indeterminate status while the server prepares the image', () => {
    render(<ImageUpload onUpload={vi.fn()} isLoading progress={null} />);

    expect(screen.getByRole('status')).toHaveTextContent(/preparing/i);
    expect(screen.queryByRole('button', { name: /choose a photo/i })).not.toBeInTheDocument();
  });

  it('shows a percentage while the file transfers', () => {
    render(<ImageUpload onUpload={vi.fn()} isLoading progress={0.42} />);

    expect(screen.getByRole('status')).toHaveTextContent('42%');
  });

  it.each(['frame.fits', 'photo.CR2', 'photo.nef', 'stack.tif'])(
    'accepts a %s upload',
    (name) => {
      const onUpload = vi.fn();
      render(<ImageUpload onUpload={onUpload} />);
      const file = new File(['data'], name, { type: 'application/octet-stream' });

      fireEvent.change(fileInput(), { target: { files: [file] } });

      expect(onUpload).toHaveBeenCalledWith(file);
    },
  );

  it('rejects an unsupported extension', () => {
    const onUpload = vi.fn();
    render(<ImageUpload onUpload={onUpload} />);
    const file = new File(['data'], 'photo.bmp', { type: 'image/bmp' });

    fireEvent.change(fileInput(), { target: { files: [file] } });

    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByText(/not supported/i)).toBeInTheDocument();
  });

  it('uploads a dropped file and highlights the zone while dragging over it', () => {
    const onUpload = vi.fn();
    const { container } = render(<ImageUpload onUpload={onUpload} />);
    const zone = container.querySelector('.dropzone') as HTMLElement;
    const file = new File(['data'], 'm42.jpg', { type: 'image/jpeg' });

    fireEvent.dragOver(zone);
    expect(zone).toHaveClass('dropzone-active');
    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass('dropzone-active');
    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });

    expect(onUpload).toHaveBeenCalledWith(file);
    expect(zone).not.toHaveClass('dropzone-active');
  });

  it('ignores a drop with no file', () => {
    const onUpload = vi.fn();
    const { container } = render(<ImageUpload onUpload={onUpload} />);

    fireEvent.drop(container.querySelector('.dropzone') as HTMLElement, { dataTransfer: { files: [] } });

    expect(onUpload).not.toHaveBeenCalled();
  });

  it('ignores drags and drops while an upload is running', () => {
    const onUpload = vi.fn();
    const { container } = render(<ImageUpload onUpload={onUpload} isLoading />);
    const zone = container.querySelector('.dropzone') as HTMLElement;

    fireEvent.dragOver(zone);
    expect(zone).not.toHaveClass('dropzone-active');
    fireEvent.drop(zone, { dataTransfer: { files: [new File(['x'], 'm42.jpg')] } });

    expect(onUpload).not.toHaveBeenCalled();
  });

  it('opens the file picker from the button', () => {
    render(<ImageUpload onUpload={vi.fn()} />);
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);

    fireEvent.click(screen.getByRole('button', { name: /choose a photo/i }));

    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it('ignores a picker change that carries no file', () => {
    const onUpload = vi.fn();
    render(<ImageUpload onUpload={onUpload} />);

    fireEvent.change(fileInput(), { target: { files: [] } });

    expect(onUpload).not.toHaveBeenCalled();
  });

  it('names the file going up and its size, then forgets it once the upload settles', () => {
    const onUpload = vi.fn();
    const { rerender } = render(<ImageUpload onUpload={onUpload} />);
    const big = new File([new Uint8Array(3 * 1024 * 1024)], 'stack.fits');
    fireEvent.change(fileInput(), { target: { files: [big] } });

    rerender(<ImageUpload onUpload={onUpload} isLoading progress={0.5} />);
    expect(screen.getByText(/stack\.fits/)).toHaveTextContent('3.0 MB');

    rerender(<ImageUpload onUpload={onUpload} />);
    rerender(<ImageUpload onUpload={onUpload} isLoading />);
    expect(screen.queryByText(/stack\.fits/)).not.toBeInTheDocument();
  });

  it('shows a small file size in KB, never below 1 KB', () => {
    const onUpload = vi.fn();
    const { rerender } = render(<ImageUpload onUpload={onUpload} />);
    fireEvent.change(fileInput(), { target: { files: [new File(['tiny'], 'tiny.png')] } });

    rerender(<ImageUpload onUpload={onUpload} isLoading />);

    expect(screen.getByText(/tiny\.png/)).toHaveTextContent('1 KB');
  });
});

