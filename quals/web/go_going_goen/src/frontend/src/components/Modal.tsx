import type { JSX, ReactNode } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "@fortawesome/free-solid-svg-icons";

type ModalProps = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

export const Modal = ({ title, open, onClose, children }: ModalProps): JSX.Element | null => {
  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <h3 id="modal-title">{title}</h3>
          <button type="button" className="ghost-button" onClick={onClose}>
            <span className="button-label">
              <span>Close</span>
              <FontAwesomeIcon icon={faXmark} className="button-icon" />
            </span>
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
};
