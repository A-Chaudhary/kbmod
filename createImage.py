import numpy as np
import matplotlib.mlab as mlab
import astropy.convolution as conv
import matplotlib.pyplot as plt
from astropy.io import fits

class createImage(object):

    def createSimpleBackground(self, xPixels, yPixels, backgroundLevel):
        "Creates 2-d array with given number of pixels."
        backgroundArray = np.ones((xPixels, yPixels))*backgroundLevel
        return backgroundArray

    def createStarSet(self, numImages, imSize, meanFlux, invDensity, psfSigma):
        starArray = np.zeros((imSize))
        numStars = int(imSize[0]*imSize[1]/invDensity)
        xCenters = np.random.randint(0, imSize[0], size=numStars)
        yCenters = np.random.randint(0, imSize[1], size=numStars)
        fluxArray = np.array(np.ones(numStars)*meanFlux +
                                  np.random.uniform(-0.5*meanFlux, 0.5*meanFlux, size=numStars))
        for star in range(0, numStars):
            starArray += self.createGaussianSource([xCenters[star], yCenters[star]], psfSigma,
                                                    imSize, fluxArray[star])

        starImagesArray = np.zeros((numImages, imSize[0], imSize[1]))
        for imNum in range(0, numImages):
            starImagesArray[imNum] = np.copy(starArray)

        return starImagesArray, np.transpose([xCenters, yCenters]), fluxArray

    def applyNoise(self, imageArray):
        noise_added = np.random.poisson(imageArray)
        return noise_added

    def convolveGaussian(self, image, gaussSigma):

        if (type(gaussSigma) is int) or (type(gaussSigma) is float):
            gaussSigma = np.array([gaussSigma, gaussSigma])

        gRow = conv.Gaussian1DKernel(gaussSigma[0])
        gCol = conv.Gaussian1DKernel(gaussSigma[1])
        convImage = np.copy(image)

        for rowNum in range(0, len(image)):
            convImage[rowNum] = conv.convolve(convImage[rowNum], gRow, boundary='extend')
        for col in range(0, len(image.T)):
            convImage[:,col] = conv.convolve(convImage[:,col], gCol, boundary='extend')

        return convImage

    def createGaussianSource(self, centerArr, sigmaArr, imSize, fluxVal):
        """Creates 2-D Gaussian Point Source

        centerArr: [xCenter, yCenter] in pixels
        sigmaArr: [xSigma, ySigma] in pixels
        imSize: [xPixels, yPixels]
        fluxVal: Flux value of point source"""

        sourceIm = np.zeros((imSize))
        sourceIm[centerArr[0], centerArr[1]] = fluxVal
        newSource = self.convolveGaussian(sourceIm, sigmaArr)

        return newSource

    def calcCenters(self, startLocArr, velArr, timeArr):

        startLocArr = np.array(startLocArr)
        velArr = np.array(velArr)
        centerArr = []
        for time in timeArr:
            centerArr.append(startLocArr + (velArr*time))
        return np.array(centerArr)

    def sumImage(self, imagePieces):

        shape = np.shape(imagePieces[0])
        totalImage = np.zeros((shape))
        for imagePart in imagePieces:
            totalImage += imagePart
        return totalImage

    def createSingleSet(self, outputName, startLocArr, velArr, timeArr, imSize,
                        bkgrdLevel, sourceLevel, sigmaArr, sourceNoise = True, bkgrdNoise = True,
                        addStars = True, starNoise = True, meanIntensity = None, invDensity = 30**2):

        "Create a set of images with a single gaussian psf moving over time."

        objCenters = self.calcCenters(startLocArr, velArr, timeArr)
        imageArray = np.zeros((len(timeArr), imSize[0], imSize[1]))
        varianceArray = np.zeros((len(timeArr), imSize[0], imSize[1]))
        for imNum in xrange(0, len(timeArr)):
            background = self.createSimpleBackground(imSize[0], imSize[1], bkgrdLevel)
            if bkgrdNoise == True:
                noisy_background = self.applyNoise(background)
            else:
                noisy_background = background

            if sourceNoise == True:
                source = self.createGaussianSource(objCenters[imNum], sigmaArr, imSize, np.random.poisson(sourceLevel))
            else:
                source = self.createGaussianSource(objCenters[imNum], sigmaArr, imSize, sourceLevel)

            imageArray[imNum] = self.sumImage([source, noisy_background])
            varianceArray[imNum] = noisy_background - background

        if addStars == True:
            if meanIntensity == None:
                meanIntensity = 40.*bkgrdLevel
            stars, starLocs, starFlux = self.createStarSet(len(timeArr), imSize, meanIntensity, invDensity, sigmaArr)
            if starNoise == True:
                noisy_stars = self.applyNoise(stars)
            else:
                noisy_stars = stars
            imageArray += noisy_stars
            np.savetxt(str(outputName + '_stars.dat'), starLocs)
            np.savetxt(str(outputName + '_starsFlux.dat'), starFlux)

        hdu = fits.PrimaryHDU(imageArray)
        hdu2 = fits.PrimaryHDU(varianceArray)
        hdu.writeto(str(outputName + '.fits'))
        hdu2.writeto(str(outputName + '_var.fits'))

class analyzeImage(object):

    def calcArrayLimits(self, imShape, centerX, centerY, scaleFactor, sigmaArr):

        xmin = int(centerX-(scaleFactor*sigmaArr[0]))
        xmax = int(1+centerX+(scaleFactor*sigmaArr[0]))
        ymin = int(centerY-(scaleFactor*sigmaArr[1]))
        ymax = int(1+centerY+(scaleFactor*sigmaArr[1]))
        if ((xmin < 0) | (ymin < 0) | (xmax >= imShape[0]) | (ymax >= imShape[1])):
            maxXOff = xmax-imShape[0]+1
            maxYOff = ymax-imShape[1]+1
            minXOff = xmin*(-1.)
            minYOff = ymin*(-1.)
            offset = np.max([maxXOff, maxYOff, minXOff, minYOff])
            xmin += offset
            xmax -= offset
            ymin += offset
            ymax -= offset
        else:
            offset = None

        return xmin, xmax, ymin, ymax, offset

    def createAperture(self, imShape, locationArray, sigma, scaleFactor, mask=False):

        apertureArray = np.zeros((imShape))

        if len(np.shape(sigma)) < 1:
            radius=scaleFactor*sigma
        else:
            radius = scaleFactor*sigma[0]

        if len(np.shape(locationArray)) < 2:
            locationArray = [locationArray]

        for center in locationArray:
            centerX = center[0]
            centerY = center[1]
            for ix in range(0, int(imShape[0])):
                for iy in range(0, int(imShape[1])):
                    distX = centerX - ix
                    distY = centerY - iy
                    if np.sqrt((distX**2)+(distY**2)) <= radius:
                        apertureArray[ix, iy] = 1.

        if mask==True:
            apertureArray -= 1
            apertureArray = np.abs(apertureArray)

        return apertureArray

    def measureLikelihood(self, imageArray, objectStartArr, velArr, timeArr, psfSigma, verbose=False,
                          perturb=None, starLocs=None, background=0.):

        if len(np.shape(imageArray)) == 2:
            imageArray = [imageArray]

        if starLocs is not None:
            scaleFactor = 4.
            mask = self.createAperture(np.shape(imageArray[0]), starLocs, scaleFactor, psfSigma, mask=True)

        measureCoords = []
        multObjects = False
        if len(np.shape(objectStartArr)) > 1:
            multObjects = True
            for objStart, objVel in zip(objectStartArr, velArr):
                measureCoords.append(createImage().calcCenters(objStart, objVel, timeArr))
            measureCoords = np.array(measureCoords)
            likeArray = np.zeros(np.shape(measureCoords)[:2])

        else:
            measureCoords.append(createImage().calcCenters(objectStartArr, velArr, timeArr))
            measureCoords = np.array(measureCoords[0])
            likeArray = []

        i=0
        likeImageArray = []
        for image in imageArray:
            print str('On Image ' + str(i+1) + ' of ' + str(len(imageArray)))
            newImage = np.copy(image)
            #Normalize Likelihood images so minimum value is 0. Is this right?

            if np.min(newImage) < 0:
                newImage += np.abs(np.min(newImage))
            else:
                newImage -= np.min(newImage)
            likeMeasurements = []
            if perturb is not None:
                perturbVar = np.random.uniform(-1,1)
                xyVar = np.random.uniform(0.5,1.5)
                xyVar = int(xyVar)
                if perturbVar >= 0:
                    measureCoords[i][xyVar] += perturb
                else:
                    measureCoords[i][xyVar] -= perturb
            if starLocs is not None:
                # maskedImage = image*mask
                # if multObjects == True:
                #     taggedStarList = []
                #     for objNum in range(0, len(measureCoords)):
                #         taggedStars = starLocs[np.where(np.sqrt(np.sum(np.power(starLocs - measureCoords[objNum, i], 2),axis=1)) < psfSigma*6.)]
                #         if len(taggedStars) > 0:
                #             for tag in taggedStars:
                #                 taggedStarList.append(tuple(tag))
                #     maskStar = np.vstack({row for row in taggedStarList})
                # else:
                #     maskStar = starLocs[np.where(np.sqrt(np.sum(np.power(starLocs - measureCoords[i], 2),axis=1)) < psfSigma*6.)]
                # if len(maskStar)>0:
                #     newImage = np.copy(image)
                #     for starNum in range(0, len(maskStar)):
                #         estimateFlux = []
                #         for imNum in range(0, len(imageArray)):
                #             if imNum != i:
                #                 estimateFlux.append(self.measureFlux(imageArray[imNum], background, maskStar[starNum], [0., 0.], [0.], psfSigma))
                #         starArray = createImage().createGaussianSource(maskStar[starNum], [psfSigma, psfSigma],
                #                                                        np.shape(newImage), np.mean(estimateFlux))
                #         newImage -= starArray.T
                #
                #     addBack = self.createAperture(np.shape(image), maskStar, psfSigma, 4.).T
                #     newMask = mask+addBack
                #     maskedImage = newImage * newMask

                likelihoodImage = createImage().convolveGaussian(newImage, psfSigma)
                likelihoodImage = mask*likelihoodImage
                likelihoodMean = np.mean(likelihoodImage[np.where(likelihoodImage > 0.0)])
                if multObjects == True:
                    for objNum in range(0, np.shape(measureCoords)[0]):
                        if mask[measureCoords[objNum,i,1], measureCoords[objNum,i,0]] == 0.0:
                            likeArray[objNum, i] = 1.0
                        else:
                            likeArray[objNum, i] = likelihoodImage[measureCoords[objNum,i,1], measureCoords[objNum, i, 0]]/likelihoodMean
                else:
                    if mask[measureCoords[i,1], measureCoords[i,0]] == 0.0:
                        likeMeasurements.append(1.0)
                    else:
                        likeMeasurements.append(likelihoodImage[measureCoords[i][1], measureCoords[i][0]]/likelihoodMean)
                    likeArray.append(likeMeasurements)

            else:
                likelihoodImage = createImage().convolveGaussian(newImage, psfSigma)
                likelihoodMean = np.mean(likelihoodImage)

                if multObjects == True:
                    for objNum in range(0, np.shape(measureCoords)[0]):
                        likeArray[objNum, i] = likelihoodImage[measureCoords[objNum,i,1], measureCoords[objNum, i, 0]]/likelihoodMean
                else:
                    likeMeasurements.append(likelihoodImage[measureCoords[i][1], measureCoords[i][0]]/likelihoodMean)
                    likeArray.append(likeMeasurements)

            likeImageArray.append(likelihoodImage)
            i+=1
        if verbose == True:
            print "Trajectory Coordinates: (x,y)\n", measureCoords
            print "Likelihood values at coordinates: ", likeArray
        return likeArray, likeImageArray

    def measureFlux(self, fitsArray, background, objectStartArr, velArr, timeArr, psfSigma, verbose=False):

        measureCoords = []
        multObjects = False
        if len(np.shape(objectStartArr)) > 1:
            multObjects = True
            for objNum in range(0, len(objectStartArr)):
                measureCoords.append(createImage().calcCenters(objectStartArr[objNum], velArr[objNum], timeArr))
        else:
            measureCoords.append(createImage().calcCenters(objectStartArr, velArr, timeArr))
            measureCoords = np.array(measureCoords[0])

        if len(np.shape(fitsArray)) == 2:
            fitsArray = [fitsArray]

        if isinstance(background, np.ndarray):
            backgroundArray = background
        else:
            backgroundArray = np.ones((np.shape(fitsArray[0])))*background

        if ((type(psfSigma) != np.ndarray) | (type(psfSigma) != list)):
            psfSigma = np.ones(2)*psfSigma

        scaleFactor=2.
        gaussSize = [2*scaleFactor*psfSigma[0]+1, 2*scaleFactor*psfSigma[1]+1]
        gaussCenter = [scaleFactor*psfSigma[0], scaleFactor*psfSigma[1]]
        gaussKernel = createImage().createGaussianSource(gaussCenter, psfSigma, gaussSize, 1.)
        gaussSquared = conv.convolve(gaussKernel, gaussKernel)

        i=0
        fluxArray = []

        for image in fitsArray:

            centerX = measureCoords[i][0]
            centerY = measureCoords[i][1]
            gaussSquared = conv.convolve(gaussKernel, gaussKernel)

            xmin, xmax, ymin, ymax, offset = self.calcArrayLimits(np.shape(image), centerX, centerY,
                                                                  scaleFactor, psfSigma)
            if offset is not None:
                gaussSquared = gaussSquared[offset:-offset, offset:-offset]

            gaussImage = np.zeros((np.shape(image)))
            gaussImage[centerX, centerY] = 1.
            gaussImage = conv.convolve(gaussImage, gaussKernel, boundary='extend')

            if background == 0:
                top = np.sum(conv.convolve(image[xmin:xmax, ymin:ymax],
                                            gaussKernel, boundary='extend'))
                bottom = np.sum(gaussSquared)
            else:
                top = np.sum(conv.convolve(image[xmin:xmax, ymin:ymax]-backgroundArray[xmin:xmax, ymin:ymax],
                                            gaussKernel, boundary='extend')/backgroundArray[xmin:xmax, ymin:ymax])
                bottom = np.sum(gaussSquared/backgroundArray[xmin:xmax, ymin:ymax])
            fluxMeasured = top/bottom
            fluxArray.append(fluxMeasured)
            i+=1
        if verbose == True:
            print "Trajectory Coordinates: (x,y)\n", measureCoords
            print "Flux values at coordinates: ", fluxArray
        return fluxArray

    def trackSingleObject(self, imageArray, gaussSigma):

        objectCoords = []
        for image in imageArray:
            newImage = createImage().convolveGaussian(image, gaussSigma)
            maxIdx = np.argmax(newImage)
            objectCoords.append(np.unravel_index(maxIdx, np.shape(newImage)))
        return objectCoords

    def plotSingleTrajectory(self, imageArray, gaussSigma):

        objCoords = self.trackSingleObject(imageArray, gaussSigma)
        fig = plt.figure(figsize=(12,12))
        plt.plot(np.array(objCoords)[:,0], np.array(objCoords)[:,1], '-ko')
        plt.xlim((0, np.shape(imageArray[0])[0]))
        plt.ylim((0, np.shape(imageArray[0])[1]))

        return fig

    def calcSNR(self, image, centerArr, gaussSigma, background, imSize, apertureScale=1.6):

        if isinstance(background, np.ndarray):
            backgroundArray = background
        else:
            backgroundArray = np.ones((imSize))*background

        apertureScale = 1.6 #See derivation here: http://wise2.ipac.caltech.edu/staff/fmasci/GaussApRadius.pdf
        aperture = self.createAperture(imSize, centerArr, apertureScale, gaussSigma[0])
        sourceCounts = np.sum(image*aperture)
        if sourceCounts < 0:
            sourceCounts = 0.0
        noiseCounts = np.sum(backgroundArray*aperture)

        snr = sourceCounts/np.sqrt(sourceCounts+noiseCounts)
        return snr

    def calcTheorySNR(self, sourceFlux, centerArr, gaussSigma, background, imSize, apertureScale=1.6):

        if isinstance(background, np.ndarray):
            backgroundArray = background
        else:
            backgroundArray = np.ones((imSize))*background

        sourceTemplate = createImage().createGaussianSource(centerArr, gaussSigma, imSize, sourceFlux)

        aperture = self.createAperture(imSize, centerArr, apertureScale, gaussSigma[0])
        sourceCounts = np.sum(sourceTemplate*aperture)
        noiseCounts = np.sum(backgroundArray*aperture)

        snr = sourceCounts/np.sqrt(sourceCounts+noiseCounts)
        return snr

    def createPostageStamp(self, imageArray, objectStartArr, velArr, timeArr, gaussSigma, scaleFactor,
                           starLocs = None):

        singleImagesArray = []
        stampWidth = np.array(np.array(gaussSigma)*scaleFactor, dtype=int)
        stampImage = np.zeros(((2*stampWidth)+1))
        if len(np.shape(imageArray)) < 3:
            imageArray = [imageArray]

        measureCoords = createImage().calcCenters(objectStartArr, velArr, timeArr)
        if len(np.shape(measureCoords)) < 2:
            measureCoords = [measureCoords]
        for centerCoords in measureCoords:
            if (centerCoords[0] + stampWidth[0] + 1) > np.shape(imageArray[0])[0]:
                raise ValueError('The boundaries of your postage stamp for one of the images go off the edge')
            elif (centerCoords[0] - stampWidth[0]) < 0:
                raise ValueError('The boundaries of your postage stamp for one of the images go off the edge')
            elif (centerCoords[1] + stampWidth[1] + 1) > np.shape(imageArray[0])[1]:
                raise ValueError('The boundaries of your postage stamp for one of the images go off the edge')
            elif (centerCoords[1] - stampWidth[1]) < 0:
                raise ValueError('The boundaries of your postage stamp for one of the images go off the edge')

        i=0
        for image in imageArray:
            xmin = np.rint(measureCoords[i,0]-stampWidth[0])
            xmax = xmin + stampWidth[0]*2 + 1
            ymin = np.rint(measureCoords[i,1]-stampWidth[1])
            ymax = ymin + stampWidth[1]*2 + 1
            if starLocs is None:
                stampImage += image[xmin:xmax, ymin:ymax]
                singleImagesArray.append(image[xmin:xmax, ymin:ymax])
            else:
                starInField = False
                for star in starLocs:
                    if (star[0] > xmin-(4*gaussSigma[0])) and (star[0] < xmax+(4*gaussSigma[0])):
                        if (star[1] > ymin-(4*gaussSigma[1])) and (star[1] < ymax+(4*gaussSigma[1])):
                            print star
                            starInField = True
                if starInField == False:
                    stampImage += image[xmin:xmax, ymin:ymax]
                    singleImagesArray.append(image[xmin:xmax, ymin:ymax])
                else:
                    print 'Star in Field for Image ', str(i+1)

            i+=1
        return stampImage, singleImagesArray

    def addMask(self, imageArray, locations, gaussSigma):

        maskedArray = np.zeros((np.shape(imageArray)))
        scaleFactor = 4.
        i = 0
        for image in imageArray:
            maskedArray[i] = image * self.createAperture(np.shape(image), locations, scaleFactor, gaussSigma, mask=True)
            i+=1

        return maskedArray

    def definePossibleTrajectories(self, psfSigma, vmax, maxTimeStep):
        maxRadius = vmax*maxTimeStep
        maxSep = psfSigma*2
        numSteps = int(np.ceil(maxRadius/maxSep))*2
        theta = maxSep/maxRadius
        vRowStart = maxRadius
        vColStart = 0.
        numTraj = int(np.ceil(np.pi*2./theta))
        vRow = np.zeros(numTraj)
        vCol = np.zeros(numTraj)
        vRow[0] = vRowStart
        vCol[0] = vColStart
        for traj in range(1,numTraj):
            vRow[traj] = vRow[traj-1]*np.cos(theta) - vCol[traj-1]*np.sin(theta)
            vCol[traj] = vRow[traj-1]*np.sin(theta) + vCol[traj-1]*np.cos(theta)
        totVRow = np.zeros(numTraj*numSteps)
        totVCol = np.zeros(numTraj*numSteps)
        for stepNum in range(0, numSteps):
            totVRow[numTraj*stepNum:numTraj*(stepNum+1)] = (vRow/numSteps)*(stepNum+1)
            totVCol[numTraj*stepNum:numTraj*(stepNum+1)] = (vCol/numSteps)*(stepNum+1)
        totVRow = np.append(totVRow, 0.)
        totVCol = np.append(totVCol, 0.)
        return totVRow, totVCol, numSteps

    def findLikelyTrajectories(self, imageArray, objStart, psfSigma, vmax, maxTimeStep, timeArr,
                                background, starLocs=None, numResults = 10, returnLikeImages = False):

        vRow, vCol, numSteps = self.definePossibleTrajectories(psfSigma, vmax, maxTimeStep)
        velArr = np.array([vRow, vCol]).T

        scaleFactor = 4.
        mask = self.createAperture(np.shape(imageArray[0]), starLocs, scaleFactor, psfSigma, mask=True)

        likelihoodImages = np.zeros(np.shape(imageArray))
        likelihoodMeans = np.zeros(len(imageArray))
        for imNum in range(0, len(imageArray)):
            newImage = np.copy(imageArray[imNum])
            newImage -= np.min(newImage)
            likelihoodImages[imNum] = createImage().convolveGaussian(newImage * mask, psfSigma)
            likelihoodImages[imNum] *= mask
            likelihoodMeans[imNum] = np.mean(likelihoodImages[imNum][np.where(likelihoodImages[imNum] > 0.0)])

        topVel = np.zeros((numResults, 2))
        topT0 = np.zeros((numResults,2))
        topScores = np.zeros(numResults)
        for rowPos in range(15,45):#range(np.shape(imageArray[0])[0]):
            print rowPos
            for colPos in range(15,45):#range(np.shape(imageArray[0])[1]):
                for objVel in velArr:
                    measureCoords = np.zeros((len(timeArr), 2))
                    measureCoords[0] = [rowPos, colPos]
                    measureCoords[1:] = createImage().calcCenters([rowPos, colPos], objVel, timeArr[1:] - timeArr[0])
                    likeMeasurements = []
                    for imNum in range(0, len(likelihoodImages)):
                        if ((measureCoords[imNum][0] < np.shape(imageArray[0])[0]) and (measureCoords[imNum][1] < np.shape(imageArray[0])[1]) and
                        (measureCoords[imNum][0] > 0) and (measureCoords[imNum][1] > 0)):
                            likeMeasure = likelihoodImages[imNum][measureCoords[imNum][0], measureCoords[imNum][1]]/likelihoodMeans[imNum]
                            if likeMeasure != 0.0:
                                likeMeasurements.append(likeMeasure)
                    score = np.prod(likeMeasurements)
                    if score > np.min(topScores):
                        idx = np.argmin(topScores)
                        topScores[idx] = score
                        topT0[idx] = [rowPos, colPos]
                        topVel[idx] = objVel

        rankings = np.argsort(topScores)[-1::-1]
        print topT0[rankings]
        print topVel[rankings]
        print topScores[rankings]

        if returnLikeImages == False:
            return topT0, topVel, topScores
        else:
            return topT0[rankings], topVel[rankings], topScores[rankings], likelihoodImages
