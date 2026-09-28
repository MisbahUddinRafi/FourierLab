# FourierLab

## Description

**FourierLab** studies one question using different kinds of signals: what does the frequency-domain representation of a signal actually contain, and what happens when we remove, isolate, mix, or alter parts of it?

The project lets users directly manipulate frequency regions, magnitude, and phase, and see (or hear) the effect. The same set of operations: region masking, magnitude/phase separation, and progressive retention, is applied to an MRI image using its k-space (2D) and to an audio clip using its STFT (1D), so the project demonstrates one consistent set of signal-processing concepts across image and audio, spatial and time domains.

The project also includes a Music Lab that combines machine learning-based source separation with digital signal processing techniques for practical audio manipulation and mixing.

## Features

### MRI Module

* 2D k-Space Visualization: Display the frequency-domain representation of MRI images.

* Frequency-Domain Masking: Apply center, outer, or custom masks to k-space.

* Interactive Region Selection: Select custom regions directly on the k-space visualization for masking and reconstruction.

* Magnitude and Phase Analysis: Separately analyze the magnitude and phase components of k-space.

* Progressive Reconstruction: Study image quality as different amounts of k-space data are retained.

* Reconstruction Quality Metrics: MSE, PSNR, SSIM, and error heatmap.

* Quality Analysis Graphs: Visualize the relationship between retained data and reconstruction quality.

### Audio Module

* Waveform and Spectrogram Visualization: Display the time-domain waveform and STFT-based spectrogram.

* Time-Frequency Masking: Remove or isolate selected regions of the spectrogram.

* Interactive Region Selection: Draw custom-shaped regions directly on the spectrogram for selective masking.

* Magnitude and Phase Analysis: Separately analyze magnitude and phase information in the STFT.

* Progressive Reconstruction: Study audio quality with different amounts of frequency information.

* Audio Quality Metrics: SNR-based reconstruction quality analysis.

* Audio Comparison: Listen to and visually compare original and reconstructed signals.

### Music Lab

* Vocal and Instrumental Separation: Use the Demucs machine learning model to separate a music audio file into vocal and non-vocal (instrumental) components.

* Audio Mixing: Mix and combine the separated vocal and instrumental components using digital signal processing techniques.

* Independent Audio Processing: Work with the separated components to explore how different audio signals can be manipulated and recombined.

* Music Audio Analysis: Visualize and compare the original, vocal, and instrumental signals as part of the processing workflow.

### Shared Analysis

* Original vs. Reconstructed Comparison: Compare results visually, audibly, and numerically.

* Frequency-Domain Exploration: Directly observe how frequency information affects signal reconstruction.

* Interactive Region Manipulation: Select and manipulate custom regions in both image k-space and audio spectrograms.

* Retention vs. Quality Analysis: Apply the same experimental framework to both MRI and audio signals.

* Signal Processing Across Domains: Explore common frequency-domain concepts through MRI, audio, and music processing.

## Developers

| Name                  | Student ID |
| --------------------- | ---------- |
| Maskat Rahman         | 2305066    |
| Md. Misbah Uddin Rafi | 2305069    |

Term Project of Signals and Linear Systems Sessional (CSE 220) course.

**Department:** CSE

**University:** Bangladesh University of Engineering and Technology (BUET)

## Supervisor

**Md. Ashrafur Rahman Khan**

Lecturer

CSE, BUET
