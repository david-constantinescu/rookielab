document.addEventListener('DOMContentLoaded', function () {
    if (typeof pdfjsLib === "undefined") {
        alert("PDF.js library not loaded.");
        return;
    }

    function renderPDF(pdfUrl, canvasId, pageNum) {
        pdfjsLib.getDocument(pdfUrl).promise.then(function(pdf) {
            pdf.getPage(pageNum).then(function(page) {
                var scale = 1.5;
                var viewport = page.getViewport({ scale: scale });
                var canvas = document.getElementById(canvasId);
                var context = canvas.getContext('2d');
                canvas.height = viewport.height;
                canvas.width = viewport.width;
                page.render({ canvasContext: context, viewport: viewport });
            }).catch(function(error) {
                console.log('Error rendering PDF: ', error);
            });
        }).catch(function(error) {
            console.log('Error loading PDF: ', error);
        });
    }

    // Get the data attributes from the HTML element
    const pdfDataElement = document.getElementById('pdf-data');
    const simulationLink = pdfDataElement.getAttribute('data-simulation-link');
    const solutionLink = pdfDataElement.getAttribute('data-solution-link');
    const isUserLoggedIn = JSON.parse(pdfDataElement.getAttribute('data-user-logged-in'));

    // Render simulation PDF (only the first page for non-logged in users)
    if (simulationLink) {
        renderPDF(simulationLink, "simulation-canvas", 1); // Render first page
    }

    // Render solution PDF if logged in
    if (isUserLoggedIn && solutionLink) {
        renderPDF(solutionLink, "solution-canvas", 1); // Render first page of solution
    }
});