const canvas = document.getElementById("matrix-rain");
const ctx = canvas.getContext("2d");

function ajustarCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}

ajustarCanvas();

const caracteres =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+-<>アイウエオカキクケコサシスセソタチツテトナニヌネノ";

const tamanhoFonte = 16;

let colunas;
let gotas;

function criarChuva() {

    colunas = Math.floor(canvas.width / tamanhoFonte);

    gotas = [];

    for (let i = 0; i < colunas; i++) {
        gotas[i] = Math.random() * -100;
    }
}

criarChuva();

function desenharMatrix() {

    ctx.fillStyle = "rgba(0, 0, 0, 0.06)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#00ff41";
    ctx.font = `${tamanhoFonte}px monospace`;

    for (let i = 0; i < gotas.length; i++) {

        const caractere =
            caracteres[Math.floor(Math.random() * caracteres.length)];

        const x = i * tamanhoFonte;
        const y = gotas[i] * tamanhoFonte;

        ctx.fillText(caractere, x, y);

        if (
            y > canvas.height &&
            Math.random() > 0.975
        ) {
            gotas[i] = 0;
        }

        gotas[i]++;
    }
}

setInterval(desenharMatrix, 40);

window.addEventListener("resize", () => {

    ajustarCanvas();
    criarChuva();

});

const musicaFundo = document.getElementById("musicaFundo");

musicaFundo.volume = 0.3;

function liberarAudio() {

    musicaFundo.play()
        .then(() => {
            console.log("> AUDIO: ONLINE");
            console.log("> PAUSED:", musicaFundo.paused);

            // Só remove depois que realmente conseguiu tocar
            document.removeEventListener("click", liberarAudio);
        })
        .catch((erro) => {
            console.error("> AUDIO BLOQUEADO:", erro);
        });
}

document.addEventListener("click", liberarAudio);