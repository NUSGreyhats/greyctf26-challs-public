document.addEventListener('DOMContentLoaded', () => {
  const trigger = document.querySelector('.login-trigger');
  const modal = document.getElementById('login-modal');
  const closeBtn = document.querySelector('.modal-close');

  if (trigger && modal) {
    trigger.addEventListener('click', (event) => {
      event.preventDefault();
      modal.classList.remove('hidden');
    });
  }

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => {
      modal.classList.add('hidden');
    });
  }

  if (modal) {
    modal.addEventListener('click', (event) => {
      if (event.target === modal) {
        modal.classList.add('hidden');
      }
    });
  }
});
