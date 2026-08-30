# FourierLab

## Description

**FourierLab** studies one question using two different kinds of signals: what does the frequency-domain representation of a signal actually contain, and what happens when we remove, isolate, or alter parts of it?

The project lets users directly manipulate frequency regions, magnitude, and phase, and see (or hear) the effect. The same set of operation: region masking, magnitude/phase separation, and progressive retention, is applied to an MRI image using its k-space (2D) and to an audio clip using its STFT (1D), so the project demonstrates one consistent set of signal-processing concepts across image and audio, spatial and time domains.

## Features

### MRI Module

- 2D k-Space Visualization: Display the frequency-domain representation of MRI images.
- Frequency-Domain Masking: Apply center, outer, or custom masks to k-space.
- Magnitude and Phase Analysis: Separately analyze the magnitude and phase components of k-space.
- Progressive Reconstruction: Study image quality as different amounts of k-space data are retained.
- Reconstruction Quality Metrics: MSE, PSNR, SSIM, and error heatmap.
- Quality Analysis Graphs: Visualize the relationship between retained data and reconstruction quality.

### Audio Module

- Waveform and Spectrogram Visualization: Display the time-domain waveform and STFT-based spectrogram.
- Time-Frequency Masking: Remove or isolate selected regions of the spectrogram.
- Magnitude and Phase Analysis: Separately analyze magnitude and phase information in the STFT.
- Progressive Reconstruction: Study audio quality with different amounts of frequency information.
- Audio Quality Metrics: SNR-based reconstruction quality analysis.
- Audio Comparison: Listen to and visually compare original and reconstructed signals.

### Shared Analysis

- Original vs. Reconstructed Comparison: Compare results visually, audibly, and numerically.
- Frequency-Domain Exploration: Directly observe how frequency information affects signal reconstruction.
- Retention vs. Quality Analysis: Apply the same experimental framework to both MRI and audio signals.

## Developers

| Name | Student ID |
|---|---|
| Maskat Rahman | 2305066 |
| Md. Misbah Uddin Rafi | 2305069 |

Term Project of Signals and Linear Systems Sessional (CSE 220) course.

**Department:** CSE  
**University:** Bangladesh University of Engineering and Technology (BUET)

## Supervisor

**Md. Ashrafur Rahman Khan**  
Lecturer  
CSE, BUET