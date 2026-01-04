document.addEventListener("DOMContentLoaded", function() {

    // Auto-fechar alertas (flash messages) após 4 segundos
    setTimeout(function() {
        let alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            let bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 4000);

    console.log("Merlô Digital carregado com sucesso.");
});