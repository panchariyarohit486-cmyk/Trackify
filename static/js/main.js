// main.js — students will add JavaScript here as features are built

(function () {
    var modal  = document.getElementById('how-modal');
    if (!modal) return;                      // only runs on pages that have the modal

    var iframe  = document.getElementById('modal-iframe');
    var closeBtn = document.getElementById('modal-close');
    var trigger  = document.getElementById('how-it-works-btn');

    function openModal() {
        iframe.src = iframe.dataset.src;
        modal.classList.add('is-open');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        iframe.src = '';                     // resets src — stops video immediately
        modal.classList.remove('is-open');
        document.body.style.overflow = '';
    }

    trigger.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);

    // click on the dark backdrop (not the box itself) closes the modal
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });

    // Escape key closes the modal
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
    });
}());
